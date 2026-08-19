<script setup lang="ts">
import { ref, computed } from 'vue'
import { rawRequest } from '../api'

interface Assertion {
  label: string
  check: (status: number, body: unknown) => boolean
}

interface TestCase {
  id: string
  name: string
  protocol: string
  method: 'GET' | 'POST'
  path: string
  body?: unknown
  assertions: Assertion[]
}

interface Outcome {
  ran: boolean
  status: number
  ms: number
  results: { label: string; pass: boolean }[]
  pass: boolean
  raw: unknown
}

const isObject = (b: unknown): b is Record<string, unknown> =>
  typeof b === 'object' && b !== null

const CASES: TestCase[] = [
  {
    id: 'health',
    name: '平台健康检查',
    protocol: 'REST',
    method: 'GET',
    path: '/health',
    assertions: [
      { label: 'HTTP 200', check: (s) => s === 200 },
      {
        label: 'status = ok',
        check: (_s, b) => isObject(b) && b.status === 'ok',
      },
    ],
  },
  {
    id: 'ingest-mqtt',
    name: 'MQTT 报文接入 (DHT22)',
    protocol: 'MQTT',
    method: 'POST',
    path: '/ingest/api/v1/data',
    body: {
      schema_version: 'v1',
      device_id: 'ESP32_001_dht22',
      subsystem: 'temp_humidity',
      protocol: 'mqtt',
      measurements: [
        { type: 'temperature', value: 26.1, unit: 'celsius' },
        { type: 'humidity', value: 56.2, unit: 'percent' },
      ],
    },
    assertions: [
      { label: 'HTTP 200', check: (s) => s === 200 },
      { label: '入库成功', check: (_s, b) => isObject(b) && b.status === 'ok' },
      { label: '返回记录号', check: (_s, b) => isObject(b) && !!b.record_id },
    ],
  },
  {
    id: 'ingest-rest',
    name: 'REST 报文接入 (红外计数)',
    protocol: 'REST',
    method: 'POST',
    path: '/ingest/api/v1/data',
    body: {
      schema_version: 'v1',
      device_id: 'ESP32_002_ir',
      subsystem: 'counting',
      protocol: 'rest',
      measurements: [{ type: 'count', value: 3, unit: 'count' }],
    },
    assertions: [
      { label: 'HTTP 200', check: (s) => s === 200 },
      { label: '入库成功', check: (_s, b) => isObject(b) && b.status === 'ok' },
    ],
  },
  {
    id: 'reject-unit',
    name: '单位错误应被语义校验拒绝',
    protocol: 'SHACL',
    method: 'POST',
    path: '/ingest/api/v1/data',
    body: {
      schema_version: 'v1',
      device_id: 'ESP32_001_dht22',
      subsystem: 'temp_humidity',
      protocol: 'mqtt',
      measurements: [
        { type: 'temperature', value: 26.1, unit: 'fahrenheit' },
      ],
    },
    assertions: [
      { label: '应返回 4xx', check: (s) => s >= 400 && s < 500 },
    ],
  },
  {
    id: 'reject-range',
    name: '超量程数据应被拒绝',
    protocol: 'SHACL',
    method: 'POST',
    path: '/ingest/api/v1/data',
    body: {
      schema_version: 'v1',
      device_id: 'ESP32_001_dht22',
      subsystem: 'temp_humidity',
      protocol: 'mqtt',
      measurements: [
        { type: 'humidity', value: 999, unit: 'percent' },
      ],
    },
    assertions: [
      { label: '应返回 4xx', check: (s) => s >= 400 && s < 500 },
    ],
  },
  {
    id: 'devices',
    name: '设备注册表',
    protocol: 'REST',
    method: 'GET',
    path: '/api/v1/devices',
    assertions: [
      { label: 'HTTP 200', check: (s) => s === 200 },
      { label: '至少一台设备', check: (_s, b) => Array.isArray(b) ? b.length > 0 : isObject(b) && Array.isArray(b.items) && b.items.length > 0 },
    ],
  },
  {
    id: 'control',
    name: '远程控制指令下发',
    protocol: 'MQTT',
    method: 'POST',
    path: '/api/v1/control',
    body: { device_id: 'relay_lighting_01', action: 'on', subsystem: 'lighting' },
    assertions: [
      { label: 'HTTP 202', check: (s) => s === 202 },
      { label: '返回指令号', check: (_s, b) => isObject(b) && !!b.command_id },
    ],
  },
  {
    id: 'audit',
    name: '审计链完整性',
    protocol: 'AUDIT',
    method: 'GET',
    path: '/api/v1/security/audit/verify',
    assertions: [
      { label: 'HTTP 200', check: (s) => s === 200 },
      { label: '链未被篡改', check: (_s, b) => isObject(b) && b.valid === true },
    ],
  },
]

const outcomes = ref<Record<string, Outcome>>({})
const running = ref(false)
const selected = ref<string | null>(null)

const summary = computed(() => {
  const done = Object.values(outcomes.value).filter((o) => o.ran)
  return {
    total: CASES.length,
    run: done.length,
    passed: done.filter((o) => o.pass).length,
    failed: done.filter((o) => !o.pass).length,
  }
})

async function runCase(c: TestCase) {
  const res = await rawRequest(c.method, c.path, c.body)
  const results = c.assertions.map((a) => ({
    label: a.label,
    pass: a.check(res.status, res.body),
  }))
  outcomes.value[c.id] = {
    ran: true,
    status: res.status,
    ms: res.ms,
    results,
    pass: results.every((r) => r.pass),
    raw: res.body,
  }
}

async function runAll() {
  running.value = true
  outcomes.value = {}
  for (const c of CASES) {
    await runCase(c)
  }
  running.value = false
}

function outcomeOf(id: string): Outcome | undefined {
  return outcomes.value[id]
}
</script>

<template>
  <div class="conformance">
    <header class="bar">
      <div class="left">
        <h1>协议一致性测试</h1>
        <p>验证四种协议的接入、语义校验拒绝行为与审计链完整性。</p>
      </div>
      <div class="right">
        <div class="tally mono">
          <span class="pass">{{ summary.passed }} 通过</span>
          <span class="fail">{{ summary.failed }} 失败</span>
          <span class="dim">/ {{ summary.total }}</span>
        </div>
        <button class="run" :disabled="running" @click="runAll">
          {{ running ? '执行中…' : '运行全部用例' }}
        </button>
      </div>
    </header>

    <table class="cases">
      <thead>
        <tr>
          <th class="c-status"></th>
          <th>用例</th>
          <th class="c-proto">协议</th>
          <th class="c-path">接口</th>
          <th class="c-code">状态码</th>
          <th class="c-ms">耗时</th>
          <th class="c-assert">断言</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="c in CASES" :key="c.id">
          <tr
            class="case"
            :class="{
              pass: outcomeOf(c.id)?.pass === true,
              fail: outcomeOf(c.id)?.pass === false,
              open: selected === c.id,
            }"
            @click="selected = selected === c.id ? null : c.id"
          >
            <td class="c-status">
              <span v-if="!outcomeOf(c.id)" class="dot idle"></span>
              <span v-else-if="outcomeOf(c.id)!.pass" class="dot ok">✓</span>
              <span v-else class="dot bad">✕</span>
            </td>
            <td>{{ c.name }}</td>
            <td class="c-proto mono">{{ c.protocol }}</td>
            <td class="c-path mono">{{ c.method }} {{ c.path }}</td>
            <td class="c-code mono">{{ outcomeOf(c.id)?.status ?? '--' }}</td>
            <td class="c-ms mono">
              {{ outcomeOf(c.id) ? outcomeOf(c.id)!.ms + 'ms' : '--' }}
            </td>
            <td class="c-assert">
              <span
                v-for="r in outcomeOf(c.id)?.results ?? []"
                :key="r.label"
                class="chip"
                :class="r.pass ? 'ok' : 'bad'"
              >{{ r.label }}</span>
              <span v-if="!outcomeOf(c.id)" class="dim">未运行</span>
            </td>
          </tr>
          <tr v-if="selected === c.id && outcomeOf(c.id)" class="detail">
            <td colspan="7">
              <pre class="mono">{{ JSON.stringify(outcomeOf(c.id)!.raw, null, 2) }}</pre>
            </td>
          </tr>
        </template>
      </tbody>
    </table>

    <p class="foot">
      拒绝类用例（单位错误、超量程）返回 4xx 才算通过——平台必须挡下不合规数据，而不是照单全收。
    </p>
  </div>
</template>

<style scoped>
.conformance {
  padding: 12px 16px 20px;
}
.bar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 10px;
}
h1 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}
.bar p {
  margin: 3px 0 0;
  font-size: 11px;
  color: var(--text-faint);
}
.right {
  display: flex;
  align-items: center;
  gap: 14px;
}
.tally {
  font-size: 12px;
  display: flex;
  gap: 8px;
}
.tally .pass { color: var(--ok); }
.tally .fail { color: var(--danger); }
.tally .dim { color: var(--text-faint); }
.run {
  background: var(--surface-2);
  border: 1px solid var(--line-strong);
  color: var(--text);
  padding: 5px 14px;
  font-size: 12px;
  cursor: pointer;
}
.run:disabled { opacity: 0.5; cursor: wait; }

.cases {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.cases th {
  text-align: left;
  font-weight: 500;
  color: var(--text-faint);
  font-size: 11px;
  padding: 5px 8px;
  border-bottom: 1px solid var(--line);
}
.case td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--line);
  color: var(--text-dim);
}
.case { cursor: pointer; }
.case:hover td { background: var(--surface-2); }
.case.pass td:nth-child(2) { color: var(--text); }
.case.fail td { background: var(--danger-bg); }

.c-status { width: 24px; text-align: center; }
.c-proto { width: 70px; }
.c-path { width: 210px; color: var(--text-faint) !important; }
.c-code, .c-ms { width: 66px; }

.dot { font-size: 12px; }
.dot.ok { color: var(--ok); }
.dot.bad { color: var(--danger); }
.dot.idle::before {
  content: '';
  display: inline-block;
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--line-strong);
}

.chip {
  display: inline-block;
  font-size: 10px;
  padding: 1px 6px;
  margin: 1px 4px 1px 0;
  border: 1px solid var(--line-strong);
}
.chip.ok { color: var(--ok); border-color: var(--ok); }
.chip.bad { color: var(--danger); border-color: var(--danger); }
.dim { color: var(--text-faint); }

.detail td {
  background: var(--bg);
  padding: 0;
}
.detail pre {
  margin: 0;
  padding: 10px 14px;
  font-size: 11px;
  color: var(--text-dim);
  max-height: 240px;
  overflow: auto;
}
.foot {
  margin: 10px 0 0;
  font-size: 10px;
  color: var(--text-faint);
}
</style>
