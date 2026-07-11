/**
 * Piltover Mediasoup SFU
 * WebRTC SFU for Telegram-compatible group calls.
 * HTTP API is used by the Piltover Python backend (JoinGroupCall).
 */

const os = require('os');
const mediasoup = require('mediasoup');
const ortc = require('mediasoup/ortc');
const express = require('express');
const http = require('http');
const socketIO = require('socket.io');
const cors = require('cors');
const winston = require('winston');
require('dotenv').config();

function ipPriority(ip) {
  if (ip.startsWith('169.254.')) return 100;
  if (ip.startsWith('192.168.56.')) return 90;
  if (ip.startsWith('172.27.') || ip.startsWith('172.17.')) return 85;
  if (/^26\./.test(ip)) return 80;
  if (/^192\.168\.(0|1|2|3|4|5|7|8|9|10|11|12|13|14|15)\./.test(ip)) return 0;
  if (ip.startsWith('192.168.')) return 15;
  if (ip.startsWith('10.')) return 20;
  if (ip.startsWith('172.')) return 40;
  return 50;
}

function detectLocalIPv4() {
  const candidates = [];
  for (const entries of Object.values(os.networkInterfaces())) {
    for (const net of entries) {
      const family = net.family;
      if (family !== 'IPv4' && family !== 4) continue;
      if (net.internal) continue;
      const ip = net.address;
      candidates.push({ ip, priority: ipPriority(ip) });
    }
  }
  candidates.sort((a, b) => a.priority - b.priority);
  return candidates[0]?.ip || null;
}

function resolveAnnouncedIp() {
  const configured = (process.env.MEDIASOUP_ANNOUNCED_IP || '').trim();
  if (configured && configured !== 'auto' && configured !== '127.0.0.1') {
    return configured;
  }
  const detected = detectLocalIPv4();
  if (detected) return detected;
  return configured || '127.0.0.1';
}

const isLocalMode = (
  process.env.PILTOVER_LOCAL === '1'
  || process.env.MEDIASOUP_ANNOUNCED_IP === '127.0.0.1'
);

const config = {
  listenIp: process.env.MEDIASOUP_LISTEN_IP || (isLocalMode ? '127.0.0.1' : '0.0.0.0'),
  announcedIp: isLocalMode ? '127.0.0.1' : resolveAnnouncedIp(),
  httpPort: parseInt(process.env.PORT, 10) || 3200,
  rtcMinPort: parseInt(process.env.RTC_MIN_PORT, 10) || 10000,
  rtcMaxPort: parseInt(process.env.RTC_MAX_PORT, 10) || 10100,
  logLevel: process.env.LOG_LEVEL || 'info',
};

const logger = winston.createLogger({
  level: config.logLevel,
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.printf(({ timestamp, level, message, ...meta }) => {
      const extra = Object.keys(meta).length ? ` ${JSON.stringify(meta)}` : '';
      return `[${timestamp}] [${level.toUpperCase()}] ${message}${extra}`;
    }),
  ),
  transports: [
    new winston.transports.Console(),
    new winston.transports.File({ filename: 'mediasoup-error.log', level: 'error' }),
    new winston.transports.File({ filename: 'mediasoup-combined.log' }),
  ],
});

const TELEGRAM_OPUS_PAYLOAD_TYPE = 111;

const mediaCodecs = [
  {
    kind: 'audio',
    mimeType: 'audio/opus',
    clockRate: 48000,
    channels: 2,
    preferredPayloadType: TELEGRAM_OPUS_PAYLOAD_TYPE,
  },
  {
    kind: 'video',
    mimeType: 'video/VP8',
    clockRate: 90000,
    parameters: { 'x-google-start-bitrate': 1000 },
  },
  {
    kind: 'video',
    mimeType: 'video/H264',
    clockRate: 90000,
    parameters: {
      'packetization-mode': 1,
      'profile-level-id': '42e01f',
      'level-asymmetry-allowed': 1,
    },
  },
];

const transportOptions = {
  listenIps: [{ ip: config.listenIp, announcedIp: config.announcedIp }],
  enableUdp: true,
  enableTcp: !isLocalMode,
  preferUdp: true,
  initialAvailableOutgoingBitrate: isLocalMode ? 300_000 : 1_000_000,
  minimumAvailableOutgoingBitrate: isLocalMode ? 150_000 : 600_000,
  maxSctpMessageSize: 262144,
  maxIncomingBitrate: isLocalMode ? 600_000 : 1_500_000,
};

let worker;
let router;
const rooms = new Map();
const socketPeers = new Map();
const transportsById = new Map();
const producersById = new Map();
const peerAudioPaused = new Map();
const speakingNotifyThrottle = new Map();

const SPEAKING_NOTIFY_INTERVAL_MS = 250;
const AUDIO_LEVEL_THRESHOLD = -70;
const AUDIO_LEVEL_INTERVAL_MS = 800;

let globalAudioLevelObserver = null;

function peerAudioKey(roomId, peerId) {
  return `${roomId}:${peerId}`;
}

function isPeerAudioPaused(roomId, peerId) {
  return peerAudioPaused.get(peerAudioKey(roomId, peerId)) === true;
}

function setPeerAudioPausedFlag(roomId, peerId, paused) {
  const key = peerAudioKey(roomId, peerId);
  if (paused) {
    peerAudioPaused.set(key, true);
  } else {
    peerAudioPaused.delete(key);
  }
}

// Telegram maps incoming RTP by participant.source — consumer out_ssrc must match.
let nextConsumerSsrcOverride = null;
const originalGetConsumerRtpParameters = ortc.getConsumerRtpParameters;
ortc.getConsumerRtpParameters = function patchedGetConsumerRtpParameters(opts) {
  const params = originalGetConsumerRtpParameters(opts);
  if (nextConsumerSsrcOverride !== null && params.encodings?.length) {
    params.encodings[0].ssrc = nextConsumerSsrcOverride;
    if (params.encodings[0].rtx) {
      delete params.encodings[0].rtx;
    }
    nextConsumerSsrcOverride = null;
  }
  return params;
};

class Peer {
  constructor(id, roomId, socket = null) {
    this.id = id;
    this.roomId = roomId;
    this.socket = socket;
    this.telegramSsrc = null;
    this.transports = new Map();
    this.producers = new Map();
    this.consumers = new Map();
    this.pendingConsumers = [];
  }

  addTransport(transport, direction) {
    transport._direction = direction;
    this.transports.set(transport.id, transport);
    transportsById.set(transport.id, transport);
  }

  addProducer(producer) {
    this.producers.set(producer.id, producer);
    producersById.set(producer.id, producer);
  }

  addConsumer(consumer) {
    this.consumers.set(consumer.id, consumer);
  }

  async close(room = null) {
    for (const consumer of this.consumers.values()) consumer.close();
    this.consumers.clear();

    for (const producer of this.producers.values()) {
      await unregisterProducerForSpeaking(producer.id);
      producersById.delete(producer.id);
      producer.close();
    }
    this.producers.clear();

    for (const transport of this.transports.values()) {
      transportsById.delete(transport.id);
      transport.close();
    }
    this.transports.clear();
  }
}

function resolvePiltoverCallbackUrl() {
  const configured = (process.env.PILTOVER_CALLBACK_URL || '').trim();
  if (configured) return configured;
  const host = (process.env.PILTOVER_CALLBACK_HOST || '127.0.0.1').trim();
  const port = parseInt(process.env.PILTOVER_CALLBACK_PORT, 10) || 4431;
  return `http://${host}:${port}/api/group-call-speaking`;
}

const piltoverSpeakingCallbackUrl = resolvePiltoverCallbackUrl();

function speakingThrottleKey(roomId, peerId) {
  return `${roomId}:${peerId}`;
}

function shouldNotifySpeaking(roomId, peerId) {
  const key = speakingThrottleKey(roomId, peerId);
  const now = Date.now();
  const last = speakingNotifyThrottle.get(key) || 0;
  if (now - last < SPEAKING_NOTIFY_INTERVAL_MS) return false;
  speakingNotifyThrottle.set(key, now);
  return true;
}

async function notifyPiltoverSpeaking(roomId, peerId) {
  if (!piltoverSpeakingCallbackUrl) return;
  if (!shouldNotifySpeaking(roomId, peerId)) return;
  try {
    const response = await fetch(piltoverSpeakingCallbackUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ roomId: String(roomId), peerId: String(peerId) }),
    });
    if (!response.ok) {
      logger.warn(`Speaking callback failed room=${roomId} peer=${peerId} status=${response.status}`);
    }
  } catch (error) {
    logger.warn(`Speaking callback error room=${roomId} peer=${peerId}`, { error: error.message });
  }
}

function locateProducerContext(producerId) {
  for (const room of rooms.values()) {
    for (const peer of room.peers.values()) {
      for (const producer of peer.producers.values()) {
        if (producer.id === producerId) {
          return { roomId: room.id, peerId: peer.id, producer };
        }
      }
    }
  }
  return null;
}

async function getGlobalAudioLevelObserver() {
  if (globalAudioLevelObserver) return globalAudioLevelObserver;
  globalAudioLevelObserver = await router.createAudioLevelObserver({
    maxEntries: 20,
    threshold: AUDIO_LEVEL_THRESHOLD,
    interval: AUDIO_LEVEL_INTERVAL_MS,
  });
  globalAudioLevelObserver.on('volumes', (volumes) => {
    for (const entry of volumes) {
      const producer = entry.producer;
      if (!producer || producer.closed) continue;
      const ctx = locateProducerContext(producer.id);
      if (!ctx) continue;
      if (isPeerAudioPaused(ctx.roomId, ctx.peerId)) continue;
      logger.debug(
        `Speaking volume room=${ctx.roomId} peer=${ctx.peerId} producer=${producer.id} dBov=${entry.volume}`,
      );
      notifyPiltoverSpeaking(ctx.roomId, ctx.peerId);
    }
  });
  logger.info('Global AudioLevelObserver created');
  return globalAudioLevelObserver;
}

async function registerProducerForSpeaking(producer, roomId, peerId) {
  if (!producer || producer.kind !== 'audio' || producer.closed) return;
  const observer = await getGlobalAudioLevelObserver();
  try {
    await observer.addProducer({ producerId: producer.id });
    logger.debug(`Speaking watch producer=${producer.id} room=${roomId} peer=${peerId}`);
  } catch (error) {
    logger.warn(`AudioLevelObserver add failed producer=${producer.id}`, { error: error.message });
  }
}

async function unregisterProducerForSpeaking(producerId) {
  if (!globalAudioLevelObserver) return;
  try {
    await globalAudioLevelObserver.removeProducer({ producerId });
  } catch (error) {
    logger.debug(`AudioLevelObserver remove failed producer=${producerId}`, { error: error.message });
  }
}

class Room {
  constructor(id) {
    this.id = id;
    this.peers = new Map();
  }

  getOrCreatePeer(peerId, socket = null) {
    let peer = this.peers.get(peerId);
    if (!peer) {
      peer = new Peer(peerId, this.id, socket);
      this.peers.set(peerId, peer);
      logger.info(`Peer ${peerId} joined room ${this.id}`);
    }
    return peer;
  }

  getPeer(peerId) {
    return this.peers.get(peerId);
  }

  getAllPeers() {
    return Array.from(this.peers.values());
  }

  async removePeer(peerId) {
    const peer = this.peers.get(peerId);
    if (!peer) return true;
    await peer.close(this);
    this.peers.delete(peerId);
    speakingNotifyThrottle.delete(speakingThrottleKey(this.id, peerId));
    logger.info(`Peer ${peerId} left room ${this.id}`);
    return this.peers.size === 0;
  }

  async close() {
    for (const peer of this.peers.values()) await peer.close(this);
    this.peers.clear();
    for (const key of speakingNotifyThrottle.keys()) {
      if (key.startsWith(`${this.id}:`)) speakingNotifyThrottle.delete(key);
    }
    logger.info(`Room ${this.id} closed`);
  }
}

function getOrCreateRoom(roomId) {
  let room = rooms.get(roomId);
  if (!room) {
    room = new Room(roomId);
    rooms.set(roomId, room);
    logger.info(`Room created: ${roomId}`);
  }
  return room;
}

function getTransportParams(clientParams) {
  if (!clientParams || typeof clientParams !== 'object') return {};
  if (clientParams.transport && typeof clientParams.transport === 'object') {
    return clientParams.transport;
  }
  return clientParams;
}

function getMediaParams(clientParams) {
  if (!clientParams || typeof clientParams !== 'object') return clientParams || {};
  // Telegram LocalParams keep payload-types / rtp-hdrexts at the top level even
  // when ICE/DTLS fields are nested under "transport".
  return clientParams;
}

function dtlsRoleFromSetup(setup) {
  const value = String(setup || '').toLowerCase();
  // transport.connect() role is the REMOTE peer's DTLS role (mediasoup picks the complement).
  // setup:active  -> remote DTLS client  -> pass role "client"
  // setup:passive -> remote DTLS server  -> pass role "server"
  if (value === 'active') return 'client';
  if (value === 'passive') return 'server';
  // tgcalls GroupNetworkManager always uses SSL_SERVER.
  return 'server';
}

function clientSetupFromParams(clientParams) {
  const source = getTransportParams(clientParams);
  const fingerprints = source.fingerprints;
  if (!Array.isArray(fingerprints) || fingerprints.length === 0) return 'actpass';

  const primary = fingerprints.find(
    (fp) => String(fp.hash || fp.algorithm || '').toLowerCase() === 'sha-256',
  ) || fingerprints[0];
  return String(primary.setup || 'actpass').toLowerCase();
}

function serverSetupForClient(clientSetup) {
  const value = String(clientSetup || '').toLowerCase();
  if (value === 'active') return 'passive';
  if (value === 'passive') return 'active';
  // actpass: answer with active so the client stays passive (DTLS server).
  return 'active';
}

function extractClientDtls(clientParams) {
  const source = getTransportParams(clientParams);
  const fingerprints = source.fingerprints;
  if (!Array.isArray(fingerprints) || fingerprints.length === 0) return null;

  const primary = fingerprints.find(
    (fp) => String(fp.hash || fp.algorithm || '').toLowerCase() === 'sha-256',
  ) || fingerprints[0];

  return {
    role: dtlsRoleFromSetup(primary.setup),
    fingerprints: fingerprints.map((fp) => ({
      algorithm: fp.hash || fp.algorithm || 'sha-256',
      value: fp.fingerprint || fp.value || '',
    })).filter((fp) => fp.value),
  };
}

function buildDefaultPayloadTypes() {
  return [{
    id: TELEGRAM_OPUS_PAYLOAD_TYPE,
    name: 'opus',
    clockrate: 48000,
    channels: 2,
    parameters: { minptime: 10, useinbandfec: 1 },
    'rtcp-fbs': [
      { type: 'transport-cc', subtype: '' },
      { type: 'nack', subtype: '' },
    ],
  }];
}

function buildDefaultRtpHdrExts() {
  if (!router) return [];
  return router.rtpCapabilities.headerExtensions
    .filter((ext) => !ext.kind || ext.kind === 'audio')
    .map((ext) => ({ uri: ext.uri, id: ext.preferredId }));
}

function buildDefaultAudioRtpParameters(ssrc) {
  if (!router) return null;

  const opusCodec = router.rtpCapabilities.codecs.find(
    (codec) => codec.kind === 'audio' && codec.mimeType.toLowerCase() === 'audio/opus',
  );
  if (!opusCodec) return null;

  const headerExtensions = router.rtpCapabilities.headerExtensions
    .filter((ext) => !ext.kind || ext.kind === 'audio')
    .map((ext) => ({ uri: ext.uri, id: ext.preferredId }));

  return {
    mid: '0',
    codecs: [{
      mimeType: opusCodec.mimeType,
      payloadType: TELEGRAM_OPUS_PAYLOAD_TYPE,
      clockRate: opusCodec.clockRate,
      channels: opusCodec.channels || 2,
      parameters: { minptime: 10, useinbandfec: 1 },
      rtcpFeedback: [
        { type: 'transport-cc', parameter: '' },
        { type: 'nack', parameter: '' },
      ],
    }],
    headerExtensions,
    encodings: [{ ssrc: Number(ssrc), dtx: false }],
    rtcp: { cname: `piltover-${ssrc}`, reducedSize: true, mux: true },
  };
}

function buildAudioRtpParameters(clientParams, ssrc) {
  const root = getMediaParams(clientParams);
  const payloadTypes = root['payload-types'] || root.payloadTypes || [];
  const rtpHdrExts = root['rtp-hdrexts'] || root.rtpHdrExts || [];

  const audioPt = payloadTypes.find((pt) => {
    const name = String(pt.name || '').toLowerCase();
    return name === 'opus' || name === 'audio';
  }) || payloadTypes.find((pt) => (pt.channels || 0) > 0) || payloadTypes[0];

  if (!audioPt) {
    return buildDefaultAudioRtpParameters(ssrc);
  }

  const mimeName = String(audioPt.name || 'opus').toLowerCase();
  const mimeType = mimeName.includes('/') ? mimeName : `audio/${mimeName}`;

  return {
    mid: 'audio',
    codecs: [{
      mimeType,
      payloadType: audioPt.id,
      clockRate: audioPt.clockrate || audioPt.clockRate || 48000,
      channels: audioPt.channels || 2,
      parameters: audioPt.parameters || { minptime: 10, useinbandfec: 1 },
      rtcpFeedback: (audioPt['rtcp-fbs'] || audioPt.rtcpFbs || []).map((fb) => ({
        type: fb.type,
        parameter: fb.subtype || fb.parameter || '',
      })),
    }],
    headerExtensions: rtpHdrExts.map((ext) => ({
      uri: ext.uri,
      id: ext.id,
    })),
    encodings: [{ ssrc: Number(ssrc), dtx: false }],
    rtcp: { cname: `piltover-${ssrc}`, reducedSize: true, mux: true },
  };
}

function candidateIp(candidate) {
  if (candidate.type === 'host' || candidate.ip === '0.0.0.0' || candidate.ip === '127.0.0.1') {
    return config.announcedIp;
  }
  return candidate.ip;
}

function buildTransportFields(transport, clientSetup = 'actpass') {
  const sha256 = transport.dtlsParameters.fingerprints.find(
    (fp) => fp.algorithm.toLowerCase() === 'sha-256',
  ) || transport.dtlsParameters.fingerprints[0];

  return {
    ufrag: transport.iceParameters.usernameFragment,
    pwd: transport.iceParameters.password,
    fingerprints: sha256 ? [{
      hash: sha256.algorithm,
      fingerprint: sha256.value,
      setup: serverSetupForClient(clientSetup),
    }] : [],
    candidates: transport.iceCandidates.map((c, index) => {
      const entry = {
        component: '1',
        foundation: c.foundation || '1',
        ip: candidateIp(c),
        port: String(c.port),
        priority: String(c.priority),
        protocol: c.protocol,
        type: c.type,
        generation: '0',
        network: '1',
        id: String(index + 1),
      };
      if (c.protocol === 'tcp' && c.tcpType) {
        entry.tcptype = c.tcpType;
      }
      return entry;
    }),
  };
}

function toTelegramConnection(transport, mediaSsrc, clientParams, clientSetup = 'actpass') {
  const fields = buildTransportFields(transport, clientSetup);
  const mediaParams = getMediaParams(clientParams || {});

  // tgcalls GroupJoinResponsePayload::parse requires nested "transport".
  // Client join payload is flat; server response must be nested.
  const connection = { transport: fields, ssrc: mediaSsrc };

  const ssrcGroups = mediaParams['ssrc-groups'] || mediaParams.ssrcGroups;
  if (Array.isArray(ssrcGroups) && ssrcGroups.length > 0) {
    connection['ssrc-groups'] = ssrcGroups;
  } else {
    connection['ssrc-groups'] = [{ semantics: 'default', sources: [mediaSsrc] }];
  }

  const payloadTypes = mediaParams['payload-types'] || mediaParams.payloadTypes;
  if (Array.isArray(payloadTypes) && payloadTypes.length > 0) {
    connection['payload-types'] = payloadTypes;
  } else {
    connection['payload-types'] = buildDefaultPayloadTypes();
  }

  const rtpHdrExts = mediaParams['rtp-hdrexts'] || mediaParams.rtpHdrExts;
  if (Array.isArray(rtpHdrExts) && rtpHdrExts.length > 0) {
    connection['rtp-hdrexts'] = rtpHdrExts;
  }

  logger.info(
    `Connection for ssrc=${mediaSsrc} format=nested keys=[${Object.keys(connection).join(',')}] candidates=${fields.candidates.length}`,
  );
  return connection;
}

function isTransportUsable(transport) {
  return transport && !transport.closed && transport.dtlsState === 'connected';
}

function canReusePeerTransport(transport, peer, mediaSsrc) {
  if (!transport || transport.closed) return false;
  if (peer.telegramSsrc !== null && peer.telegramSsrc !== mediaSsrc) return false;
  if (transport.dtlsState === 'connected') return true;
  const iceReady = transport.iceState === 'connected' || transport.iceState === 'completed';
  return iceReady && (transport.dtlsState === 'connecting' || transport.dtlsState === 'new');
}

function closePeerSendTransports(peer) {
  for (const [transportId, transport] of peer.transports) {
    if (transport._direction !== 'send') continue;
    transport.close();
    peer.transports.delete(transportId);
    transportsById.delete(transportId);
  }
}

function prunePeerSendTransport(peer, transport) {
  for (const consumer of peer.consumers.values()) {
    if (consumer.closed) peer.consumers.delete(consumer.id);
  }
  for (const producer of peer.producers.values()) {
    if (producer.closed) {
      producersById.delete(producer.id);
      peer.producers.delete(producer.id);
    }
  }
  if (!transport) return;
  peer.transports.delete(transport.id);
  transportsById.delete(transport.id);
}

async function flushPendingConsumers(peer) {
  if (!peer.pendingConsumers.length) return;
  const pending = peer.pendingConsumers.splice(0, peer.pendingConsumers.length);
  const room = rooms.get(peer.roomId);
  if (!room) return;
  for (const { producerId, producerPeerId } of pending) {
    const producerPeer = room.getPeer(producerPeerId);
    const producer = producerPeer?.producers.get(producerId)
      ?? producersById.get(producerId);
    if (!producer || producer.closed) continue;
    await createConsumerForPeer(peer, producer, producerPeer);
  }
}

function bindTransportLifecycle(peer, transport) {
  transport.on('dtlsstatechange', (dtlsState) => {
    if (dtlsState === 'connected') {
      flushPendingConsumers(peer).catch((error) => {
        logger.error(`Failed to flush pending consumers for peer ${peer.id}`, { error: error.message });
      });
    }
    if (dtlsState === 'closed') {
      logger.info(`Transport ${transport.id} DTLS closed for peer ${peer.id}, pruning`);
      prunePeerSendTransport(peer, transport);
    }
  });
}

async function createWebRtcTransport(peer = null) {
  const transport = await router.createWebRtcTransport(transportOptions);

  transport.on('icestatechange', (iceState) => {
    if (iceState === 'failed' || iceState === 'disconnected') {
      logger.warn(`Transport ${transport.id} ICE state: ${iceState}`);
    } else {
      logger.debug(`Transport ${transport.id} ICE state: ${iceState}`);
    }
  });

  transport.on('iceselectedtuplechange', (tuple) => {
    logger.debug(
      `Transport ${transport.id} ICE selected tuple: ${tuple.protocol} ${tuple.localIp}:${tuple.localPort} -> ${tuple.remoteIp}:${tuple.remotePort}`,
    );
  });

  transport.on('dtlsstatechange', (dtlsState) => {
    if (dtlsState === 'failed' || dtlsState === 'closed') {
      logger.warn(`Transport ${transport.id} DTLS state: ${dtlsState}`);
    } else {
      logger.debug(`Transport ${transport.id} DTLS state: ${dtlsState}`);
    }
  });

  transport.on('sctpstatechange', (sctpState) => {
    logger.debug(`Transport ${transport.id} SCTP state: ${sctpState}`);
  });

  transport.on('@close', () => {
    transportsById.delete(transport.id);
    if (peer) prunePeerSendTransport(peer, transport);
  });

  if (peer) bindTransportLifecycle(peer, transport);

  return transport;
}

function getPeerSendTransport(peer) {
  for (const transport of peer.transports.values()) {
    if (transport._direction === 'send') return transport;
  }
  const first = peer.transports.values().next();
  return first.done ? null : first.value;
}

function queuePendingConsumer(peer, producer, producerPeer) {
  const entry = { producerId: producer.id, producerPeerId: producerPeer.id };
  if (peer.pendingConsumers.some((item) => item.producerId === entry.producerId)) return;
  peer.pendingConsumers.push(entry);
  logger.info(
    `Queued consumer for peer ${peer.id} producer ${producer.id} until DTLS connected`,
  );
}

async function createConsumerForPeer(peer, producer, producerPeer) {
  const transport = getPeerSendTransport(peer);
  if (!transport || transport.closed) {
    logger.warn(`No transport for peer ${peer.id} to consume producer ${producer.id}`);
    return null;
  }
  if (!isTransportUsable(transport)) {
    queuePendingConsumer(peer, producer, producerPeer);
    return null;
  }

  for (const consumer of peer.consumers.values()) {
    if (consumer.producerId === producer.id) return consumer;
  }

  if (!router.canConsume({ producerId: producer.id, rtpCapabilities: router.rtpCapabilities })) {
    logger.warn(`Router cannot consume producer ${producer.id} for peer ${peer.id}`);
    return null;
  }

  const targetSsrc = producerPeer?.telegramSsrc ?? producer.appData?.telegramSsrc;
  if (!targetSsrc) {
    logger.warn(`No telegram SSRC for producer ${producer.id} peer ${producerPeer?.id}`);
    return null;
  }

  try {
    nextConsumerSsrcOverride = Number(targetSsrc);
    const startPaused = isPeerAudioPaused(peer.roomId, producerPeer.id);
    const consumer = await transport.consume({
      producerId: producer.id,
      rtpCapabilities: router.rtpCapabilities,
      paused: startPaused,
      enableRtx: false,
    });
    peer.addConsumer(consumer);
    consumer.on('transportclose', () => peer.consumers.delete(consumer.id));
    consumer.on('producerclose', () => peer.consumers.delete(consumer.id));
    if (!startPaused && consumer.paused) await consumer.resume();
    const outSsrc = consumer.rtpParameters?.encodings?.[0]?.ssrc;
    logger.info(
      `Consumer ${consumer.id} on peer ${peer.id} for producer ${producer.id} telegram_ssrc=${targetSsrc} out_ssrc=${outSsrc}`,
    );
    return consumer;
  } catch (error) {
    nextConsumerSsrcOverride = null;
    logger.error(`Failed to create consumer for peer ${peer.id}`, { error: error.message });
    return null;
  }
}

async function pipeProducerToAllPeers(room, producerPeer, producer) {
  for (const otherPeer of room.getAllPeers()) {
    if (otherPeer.id === producerPeer.id) continue;
    await createConsumerForPeer(otherPeer, producer, producerPeer);
  }
}

async function pipeExistingProducersToPeer(room, newPeer) {
  for (const otherPeer of room.getAllPeers()) {
    if (otherPeer.id === newPeer.id) continue;
    for (const producer of otherPeer.producers.values()) {
      await createConsumerForPeer(newPeer, producer, otherPeer);
    }
  }
}

async function createAudioProducer(peer, transport, clientParams, mediaSsrc) {
  const rtpParameters = buildAudioRtpParameters(clientParams, mediaSsrc);
  if (!rtpParameters) {
    logger.warn(`Could not build audio RTP parameters for peer ${peer.id}`);
    return null;
  }

  const producer = await transport.produce({
    kind: 'audio',
    rtpParameters,
    appData: { telegramSsrc: mediaSsrc },
  });
  peer.telegramSsrc = mediaSsrc;
  peer.addProducer(producer);
  producer.on('transportclose', () => {
    peer.producers.delete(producer.id);
    producersById.delete(producer.id);
  });
  registerProducerForSpeaking(producer, peer.roomId, peer.id).catch((error) => {
    logger.error(`Failed to register producer ${producer.id} for speaking detection`, { error: error.message });
  });
  return producer;
}

async function notifyNewProducer(room, producerPeer, producer) {
  await pipeProducerToAllPeers(room, producerPeer, producer);
  for (const otherPeer of room.getAllPeers()) {
    if (otherPeer.id === producerPeer.id) continue;
    if (otherPeer.socket) {
      otherPeer.socket.emit('new-producer', {
        peerId: producerPeer.id,
        producerId: producer.id,
        kind: producer.kind,
      });
    }
  }
}

async function createWorker() {
  worker = await mediasoup.createWorker({
    logLevel: 'warn',
    rtcMinPort: config.rtcMinPort,
    rtcMaxPort: config.rtcMaxPort,
  });

  worker.on('died', () => {
    logger.error('Mediasoup worker died, exiting in 2 seconds');
    setTimeout(() => process.exit(1), 2000);
  });

  logger.info(`Mediasoup worker created [pid=${worker.pid}]`);
}

async function createRouter() {
  router = await worker.createRouter({ mediaCodecs });
  logger.info(`Mediasoup router created [id=${router.id}]`);
}

const app = express();
app.use(cors());
app.use(express.json({ limit: '1mb' }));

const server = http.createServer(app);
const io = socketIO(server, { cors: { origin: '*', methods: ['GET', 'POST'] } });

app.get('/health', (_req, res) => {
  res.json({
    status: 'healthy',
    worker: { pid: worker?.pid, closed: worker?.closed },
    router: { id: router?.id, closed: router?.closed },
    rooms: rooms.size,
    peers: Array.from(rooms.values()).reduce((n, r) => n + r.peers.size, 0),
  });
});

app.get('/api/rtp-capabilities', (_req, res) => {
  if (!router) return res.status(503).json({ error: 'Router not initialized' });
  res.json(router.rtpCapabilities);
});

app.get('/api/dtls-fingerprint', async (_req, res) => {
  if (!router) return res.status(503).json({ error: 'Router not initialized' });

  try {
    const transport = await createWebRtcTransport();
    const fp = transport.dtlsParameters.fingerprints.find(
      (f) => f.algorithm.toLowerCase() === 'sha-256',
    ) || transport.dtlsParameters.fingerprints[0];
    transport.close();
    res.json({ algorithm: fp.algorithm, value: fp.value });
  } catch (error) {
    logger.error('Failed to get DTLS fingerprint', { error: error.message });
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/rooms/:roomId', (req, res) => {
  const room = rooms.get(req.params.roomId);
  if (!room) return res.status(404).json({ error: 'Room not found' });

  res.json({
    id: room.id,
    peers: room.getAllPeers().map((p) => ({
      id: p.id,
      producers: p.producers.size,
      consumers: p.consumers.size,
    })),
  });
});

app.delete('/api/rooms/:roomId', async (req, res) => {
  const room = rooms.get(req.params.roomId);
  if (!room) return res.status(404).json({ error: 'Room not found' });
  await room.close();
  rooms.delete(room.id);
  res.json({ success: true });
});

async function setPeerAudioPaused(roomId, peerId, paused) {
  const room = rooms.get(String(roomId));
  if (!room) return;
  const targetPeer = room.getPeer(String(peerId));
  if (!targetPeer) return;

  if (isPeerAudioPaused(roomId, peerId) === paused) {
    return;
  }

  setPeerAudioPausedFlag(roomId, peerId, paused);

  const targetProducerIds = new Set();
  for (const producer of targetPeer.producers.values()) {
    if (producer.kind !== 'audio' || producer.closed) continue;
    targetProducerIds.add(producer.id);
    if (paused) {
      if (!producer.paused) await producer.pause();
    } else if (producer.paused) {
      await producer.resume();
    }
  }

  let consumerCount = 0;
  for (const peer of room.getAllPeers()) {
    for (const consumer of peer.consumers.values()) {
      if (!targetProducerIds.has(consumer.producerId)) continue;
      consumerCount += 1;
      if (paused) {
        if (!consumer.paused) await consumer.pause();
      } else if (consumer.paused) {
        await consumer.resume();
      }
    }
  }
  logger.info(
    `Peer ${peerId} room ${roomId} audio paused=${paused} producers=${targetProducerIds.size} consumers=${consumerCount}`,
  );
}

app.post('/api/participant-state', async (req, res) => {
  try {
    const { roomId, peerId, paused } = req.body;
    if (!roomId || !peerId || paused === undefined) {
      return res.status(400).json({ error: 'roomId, peerId and paused are required' });
    }
    await setPeerAudioPaused(roomId, peerId, Boolean(paused));
    res.json({ success: true });
  } catch (error) {
    logger.error('Error in /api/participant-state', { error: error.message });
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/leave', async (req, res) => {
  try {
    const { roomId, peerId } = req.body;
    if (!roomId || !peerId) {
      return res.status(400).json({ error: 'roomId and peerId are required' });
    }

    const room = rooms.get(String(roomId));
    if (!room) return res.json({ success: true });

    peerAudioPaused.delete(peerAudioKey(roomId, peerId));
    const empty = await room.removePeer(String(peerId));
    if (empty) {
      for (const key of peerAudioPaused.keys()) {
        if (key.startsWith(`${roomId}:`)) peerAudioPaused.delete(key);
      }
      await room.close();
      rooms.delete(room.id);
      logger.info(`Room ${roomId} closed after last peer left`);
    }
    res.json({ success: true });
  } catch (error) {
    logger.error('Error in /api/leave', { error: error.message });
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/join', async (req, res) => {
  try {
    const { roomId, peerId, ssrc, clientParams } = req.body;
    if (!roomId || !peerId || !ssrc) {
      return res.status(400).json({ error: 'roomId, peerId and ssrc are required' });
    }

    const mediaParams = getMediaParams(clientParams);
    const mediaSsrc = Number(mediaParams.ssrc ?? ssrc);

    const room = getOrCreateRoom(String(roomId));
    const peer = room.getOrCreatePeer(String(peerId));

    const paramKeys = clientParams && typeof clientParams === 'object'
      ? Object.keys(clientParams).join(',')
      : 'none';
    const payloadTypes = mediaParams['payload-types'] || mediaParams.payloadTypes || [];
    const clientCandidates = (getTransportParams(clientParams).candidates || []).length;
    logger.info(
      `Join peer ${peerId} room ${roomId} ssrc=${mediaSsrc} keys=[${paramKeys}] payload-types=${payloadTypes.length} client-candidates=${clientCandidates}`,
    );

    const clientSetup = clientSetupFromParams(clientParams);
    logger.info(`Join peer ${peerId} client DTLS setup=${clientSetup}`);

    let transport = getPeerSendTransport(peer);
    if (canReusePeerTransport(transport, peer, mediaSsrc)) {
      logger.info(
        `Reusing transport ${transport.id} for peer ${peerId} ssrc=${mediaSsrc} ice=${transport.iceState} dtls=${transport.dtlsState}`,
      );
      return res.json(toTelegramConnection(transport, mediaSsrc, clientParams, clientSetup));
    }

    if (peer.telegramSsrc !== null && peer.telegramSsrc !== mediaSsrc) {
      logger.info(
        `Peer ${peerId} rejoining room ${roomId} with new ssrc ${mediaSsrc} (was ${peer.telegramSsrc})`,
      );
    }

    closePeerSendTransports(peer);
    peer.pendingConsumers = [];
    transport = await createWebRtcTransport(peer);
    peer.addTransport(transport, 'send');

    const clientDtls = extractClientDtls(clientParams);
    if (clientDtls?.fingerprints.length) {
      await transport.connect({ dtlsParameters: clientDtls });
      const serverSetup = serverSetupForClient(clientSetup);
      logger.info(
        `Transport ${transport.id} DTLS configured for peer ${peerId} remote_role=${clientDtls.role} local_role=${transport.dtlsParameters.role} client_setup=${clientSetup} server_setup=${serverSetup}`,
      );
    } else {
      logger.warn(`No client DTLS fingerprints for peer ${peerId} in room ${roomId}`);
    }

    try {
      const producer = await createAudioProducer(peer, transport, clientParams, mediaSsrc);
      if (producer) {
        if (isPeerAudioPaused(roomId, peerId)) {
          await producer.pause();
        }
        await notifyNewProducer(room, peer, producer);
        await pipeExistingProducersToPeer(room, peer);
        if (isTransportUsable(transport)) {
          await flushPendingConsumers(peer);
        }
        logger.info(
          `Producer ${producer.id} created for peer ${peerId} ssrc=${mediaSsrc} fallback=${payloadTypes.length === 0}`,
        );
      }
    } catch (produceError) {
      logger.error(`Failed to create producer for peer ${peerId}`, { error: produceError.message });
    }

    res.json(toTelegramConnection(transport, mediaSsrc, clientParams, clientSetup));
  } catch (error) {
    logger.error('Error in /api/join', { error: error.message });
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/transports/create', async (req, res) => {
  try {
    const { roomId, peerId, direction = 'send' } = req.body;
    if (!roomId || !peerId) {
      return res.status(400).json({ error: 'roomId and peerId are required' });
    }

    const room = getOrCreateRoom(String(roomId));
    const peer = room.getOrCreatePeer(String(peerId));
    if (direction === 'send') {
      closePeerSendTransports(peer);
    }
    const transport = await createWebRtcTransport();
    peer.addTransport(transport, direction);

    const tuple = transport.tuple;
    logger.info(
      `Transport ${transport.id} created [room=${roomId}, peer=${peerId}, dir=${direction}, local=${tuple?.localIp}:${tuple?.localPort}]`,
    );

    res.json({
      id: transport.id,
      iceParameters: transport.iceParameters,
      iceCandidates: transport.iceCandidates,
      dtlsParameters: transport.dtlsParameters,
    });
  } catch (error) {
    logger.error('Error creating transport', { error: error.message });
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/transports/connect', async (req, res) => {
  try {
    const { transportId, dtlsParameters } = req.body;
    const transport = transportsById.get(transportId);
    if (!transport) return res.status(404).json({ error: 'Transport not found' });

    await transport.connect({ dtlsParameters });
    logger.info(`Transport ${transportId} connected`);
    res.json({ success: true });
  } catch (error) {
    logger.error('Error connecting transport', { error: error.message });
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/produce', async (req, res) => {
  try {
    const { transportId, kind, rtpParameters, roomId, peerId } = req.body;
    const transport = transportsById.get(transportId);
    if (!transport) return res.status(404).json({ error: 'Transport not found' });

    const producer = await transport.produce({ kind, rtpParameters });

    let room;
    let peer;
    if (roomId && peerId) {
      room = rooms.get(String(roomId));
      peer = room?.getPeer(String(peerId));
    }
    if (peer) {
      peer.addProducer(producer);
      producer.on('transportclose', () => {
        peer.producers.delete(producer.id);
        producersById.delete(producer.id);
      });
      if (room) {
        if (kind === 'audio') {
          await registerProducerForSpeaking(producer, room.id, peer.id);
        }
        await notifyNewProducer(room, peer, producer);
      }
    } else {
      producersById.set(producer.id, producer);
    }

    logger.info(`Producer ${producer.id} created [kind=${kind}]`);
    res.json({ producerId: producer.id });
  } catch (error) {
    logger.error('Error creating producer', { error: error.message });
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/consume', async (req, res) => {
  try {
    const { transportId, producerId, rtpCapabilities, roomId, peerId } = req.body;
    const transport = transportsById.get(transportId);
    if (!transport) return res.status(404).json({ error: 'Transport not found' });

    if (!router.canConsume({ producerId, rtpCapabilities })) {
      return res.status(400).json({ error: 'Cannot consume' });
    }

    const consumer = await transport.consume({ producerId, rtpCapabilities, paused: false });

    if (roomId && peerId) {
      const room = rooms.get(String(roomId));
      const peer = room?.getPeer(String(peerId));
      if (peer) {
        peer.addConsumer(consumer);
        consumer.on('transportclose', () => peer.consumers.delete(consumer.id));
        consumer.on('producerclose', () => peer.consumers.delete(consumer.id));
      }
    }

    res.json({
      id: consumer.id,
      producerId,
      kind: consumer.kind,
      rtpParameters: consumer.rtpParameters,
    });
  } catch (error) {
    logger.error('Error creating consumer', { error: error.message });
    res.status(500).json({ error: error.message });
  }
});

io.on('connection', (socket) => {
  logger.info(`Socket connected: ${socket.id}`);

  socket.on('join-room', async ({ roomId, peerId }, callback) => {
    try {
      const room = getOrCreateRoom(String(roomId));
      const peer = room.getOrCreatePeer(String(peerId), socket);
      socketPeers.set(socket.id, peer);
      socket.join(String(roomId));
      callback({ success: true, rtpCapabilities: router.rtpCapabilities });
    } catch (error) {
      callback({ success: false, error: error.message });
    }
  });

  socket.on('create-transport', async ({ direction = 'send' }, callback) => {
    try {
      const peer = socketPeers.get(socket.id);
      if (!peer) throw new Error('Peer not found');

      const transport = await createWebRtcTransport();
      peer.addTransport(transport, direction);

      callback({
        success: true,
        transport: {
          id: transport.id,
          iceParameters: transport.iceParameters,
          iceCandidates: transport.iceCandidates,
          dtlsParameters: transport.dtlsParameters,
        },
      });
    } catch (error) {
      callback({ success: false, error: error.message });
    }
  });

  socket.on('connect-transport', async ({ transportId, dtlsParameters }, callback) => {
    try {
      const peer = socketPeers.get(socket.id);
      if (!peer) throw new Error('Peer not found');
      const transport = peer.transports.get(transportId);
      if (!transport) throw new Error('Transport not found');

      await transport.connect({ dtlsParameters });
      callback({ success: true });
    } catch (error) {
      callback({ success: false, error: error.message });
    }
  });

  socket.on('produce', async ({ transportId, kind, rtpParameters }, callback) => {
    try {
      const peer = socketPeers.get(socket.id);
      if (!peer) throw new Error('Peer not found');
      const transport = peer.transports.get(transportId);
      if (!transport) throw new Error('Transport not found');

      const producer = await transport.produce({ kind, rtpParameters });
      peer.addProducer(producer);
      producer.on('transportclose', () => {
        peer.producers.delete(producer.id);
        producersById.delete(producer.id);
      });

      const room = rooms.get(peer.roomId);
      if (room) {
        if (kind === 'audio') {
          await registerProducerForSpeaking(producer, room.id, peer.id);
        }
        await notifyNewProducer(room, peer, producer);
      }

      callback({ success: true, producerId: producer.id });
    } catch (error) {
      callback({ success: false, error: error.message });
    }
  });

  socket.on('consume', async ({ transportId, producerId, rtpCapabilities }, callback) => {
    try {
      const peer = socketPeers.get(socket.id);
      if (!peer) throw new Error('Peer not found');
      const transport = peer.transports.get(transportId);
      if (!transport) throw new Error('Transport not found');

      if (!router.canConsume({ producerId, rtpCapabilities })) {
        throw new Error('Cannot consume');
      }

      const consumer = await transport.consume({ producerId, rtpCapabilities, paused: false });
      peer.addConsumer(consumer);
      consumer.on('transportclose', () => peer.consumers.delete(consumer.id));
      consumer.on('producerclose', () => {
        socket.emit('consumer-closed', { consumerId: consumer.id });
        peer.consumers.delete(consumer.id);
      });

      callback({
        success: true,
        consumer: {
          id: consumer.id,
          producerId,
          kind: consumer.kind,
          rtpParameters: consumer.rtpParameters,
        },
      });
    } catch (error) {
      callback({ success: false, error: error.message });
    }
  });

  socket.on('disconnect', () => {
    const peer = socketPeers.get(socket.id);
    if (!peer) return;

    const room = rooms.get(peer.roomId);
    if (room) {
      room.removePeer(peer.id).then((empty) => {
        if (empty) rooms.delete(room.id);
      }).catch((error) => {
        logger.error(`Failed to remove peer ${peer.id} on disconnect`, { error: error.message });
      });
      socket.to(peer.roomId).emit('peer-left', { peerId: peer.id });
    }
    socketPeers.delete(socket.id);
  });
});

async function startServer() {
  await createWorker();
  await createRouter();

  server.listen(config.httpPort, config.listenIp, () => {
    logger.info('Piltover Mediasoup SFU started');
    logger.info(`HTTP API: http://${config.listenIp}:${config.httpPort}`);
    logger.info(`WebRTC ports: ${config.rtcMinPort}-${config.rtcMaxPort}`);
    logger.info(`Announced IP: ${config.announcedIp}`);
    logger.info(`Speaking callback: ${piltoverSpeakingCallbackUrl}`);
    if (process.env.MEDIASOUP_ANNOUNCED_IP === '127.0.0.1') {
      logger.info('Local mode: clients use 127.0.0.1 for WebRTC');
    } else if (config.announcedIp !== '127.0.0.1') {
      logger.info(`WebRTC candidates use LAN IP ${config.announcedIp} (set public_ip in system.toml to match)`);
    }
  });
}

process.on('SIGINT', () => {
  logger.info('Shutting down...');
  Promise.all([...rooms.values()].map((room) => room.close())).finally(() => {
    rooms.clear();
    socketPeers.clear();
    transportsById.clear();
    producersById.clear();
    if (worker) worker.close();
    server.close(() => process.exit(0));
  });
});

startServer().catch((error) => {
  logger.error('Failed to start server', { error: error.message });
  process.exit(1);
});