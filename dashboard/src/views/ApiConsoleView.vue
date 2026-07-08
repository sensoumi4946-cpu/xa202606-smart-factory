<script setup lang="ts">
// Tab 2: manual API debugging console. Left column lists the eight public
// endpoints; the right column shows method/url, an editable params or JSON
// body field and a Send button that issues a real request via rawRequest.
// Nothing polls here — the user drives every call by hand.
import { ref, computed } from 'vue'
import { rawRequest, type RawResult } from '../api'
import JsonViewer from '../components/JsonViewer.vue'

interface Endpoint {
  id: string
  method: string
  path: string
  desc: string
  params?: string
  body?: string
}

const DATA_TMPL = JSON.stringify(
  {
    schema_version: 'v1',
    device_id: 'sensor_dht22_01',
    subsystem: 'temp_humidity',
    protocol: 'mqtt',
    measurements: [{ type: 'temperature', value: 25.3, unit: 'celsius' }],
  },
  null,
  2,
)

const CTRL_TMPL = JSON.stringify(
  { device_id: 'sensor_pir_01', action: 'relay', params: { state: 'on' } },
  null,
  2,
)

const ENDPOINTS: Endpoint[] = [
  { id: 'health', method: 'GET', path: 'health', desc: '服务健康检查' },
  { id: 'latest', method: 'GET', path: 'api/v1/latest', desc: '各设备最新读数' },
  {
    id: 'history',
    method: 'GET',
    path: 'api/v1/history',
    desc: '历史记录查询',
    params: 'limit=10',
  },
  {
    id: 'alerts',
    method: 'GET',
    path: 'api/v1/alerts',
    desc: '查询告警记录',
    params: 'limit=10',
  },
  {
    id: 'semantic',
    method: 'GET',
    path: 'api/v1/semantic',
    desc: '语义视图 (SPARQL)',
    params: 'view=sensor-observations',
  },
  { id: 'devices', method: 'GET', path: 'api/v1/devices', desc: '设备 ID 列表' },
  {
    id: 'data',
    method: 'POST',
    path: 'api/v1/data',
    desc: '写入传感器数据',
    body: DATA_TMPL,
  },
  {
    id: 'control',
    method: 'POST',
    path: 'api/v1/control',
    desc: '下发远程控制指令',
    body: CTRL_TMPL,
  },
]

const selected = ref<Endpoint>(ENDPOINTS[0])
const params = ref('')
const body = ref('')
const result = ref<RawResult | null>(null)
const errMsg = ref('')
const sending = ref(false)

function select(ep: Endpoint) {
  selected.value = ep
  params.value = ep.params ?? ''
  body.value = ep.body ?? ''
  result.value = null
  errMsg.value = ''
}
select(ENDPOINTS[0])

const fullUrl = computed(() => {
  const base = '/' + selected.value.path
  if (selected.value.method === 'GET' && params.value.trim()) {
    return base + '?' + params.value.trim()
  }
  return base
})

async function send() {
  sending.value = true
  errMsg.value = ''
  result.value = null
  try {
    let payload: unknown
    if (selected.value.method === 'POST') {
      payload = JSON.parse(body.value || '{}')
    }
    result.value = await rawRequest(
      selected.value.method,
      fullUrl.value,
      payload,
    )
  } catch (e) {
    errMsg.value =
      '请求失败: ' + (e instanceof Error ? e.message : String(e))
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <div class="console-view">
    <aside class="endpoints">
      <h3>Endpoints</h3>
      <button
        v-for="ep in ENDPOINTS"
        :key="ep.id"
        class="ep"
        :class="{ active: selected.id === ep.id }"
        @click="select(ep)"
      >
        <span class="verb" :class="ep.method.toLowerCase()">{{ ep.method }}</span>
        <span class="path">/{{ ep.path }}</span>
      </button>
    </aside>

    <section class="req">
      <div class="line">
        <span class="verb" :class="selected.method.toLowerCase()">
          {{ selected.method }}
        </span>
        <code class="url">{{ fullUrl }}</code>
      </div>
      <p class="desc">{{ selected.desc }}</p>

      <label v-if="selected.method === 'GET'" class="field">
        <span>Params</span>
        <input v-model="params" placeholder="key=value&key2=value2" />
      </label>
      <label v-else class="field">
        <span>Body (JSON)</span>
        <textarea v-model="body" rows="9"></textarea>
      </label>

      <button class="send" :disabled="sending" @click="send">
        {{ sending ? '发送中...' : 'Send' }}
      </button>

      <div v-if="errMsg" class="err">{{ errMsg }}</div>
      <div v-if="result" class="resp">
        <div class="status-line">
          <span class="code" :class="{ ok: result.ok }">{{ result.status }}</span>
          <span class="time">{{ result.ms }}ms</span>
        </div>
        <JsonViewer :value="result.body" />
      </div>
    </section>
  </div>
</template>

<style scoped>
.console-view {
  display: grid;
  grid-template-columns: 240px 1fr;
  gap: 16px;
}
.endpoints {
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid #334155;
  border-radius: 10px;
  padding: 12px;
}
h3 {
  color: #38bdf8;
  font-size: 0.9rem;
  margin: 0 0 10px;
}
.ep {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  background: transparent;
  border: none;
  border-radius: 6px;
  padding: 6px 8px;
  cursor: pointer;
  text-align: left;
  margin-bottom: 2px;
}
.ep:hover {
  background: #0f172a;
}
.ep.active {
  background: #0f172a;
}
.verb {
  font-size: 0.66rem;
  font-weight: 700;
  border-radius: 3px;
  padding: 1px 5px;
}
.verb.get {
  background: #164e63;
  color: #67e8f9;
}
.verb.post {
  background: #422006;
  color: #fbbf24;
}
.path {
  font-family: monospace;
  font-size: 0.74rem;
  color: #cbd5e1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.req {
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid #334155;
  border-radius: 10px;
  padding: 16px;
}
.line {
  display: flex;
  align-items: center;
  gap: 10px;
}
.url {
  font-family: monospace;
  font-size: 0.85rem;
  color: #7dd3fc;
}
.desc {
  color: #94a3b8;
  font-size: 0.8rem;
  margin: 6px 0 14px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-bottom: 12px;
}
.field span {
  color: #94a3b8;
  font-size: 0.78rem;
}
.field input,
.field textarea {
  background: #0f172a;
  color: #e2e8f0;
  border: 1px solid #334155;
  border-radius: 6px;
  padding: 8px 10px;
  font-family: monospace;
  font-size: 0.8rem;
}
.send {
  background: #0e7490;
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 8px 24px;
  cursor: pointer;
  font-size: 0.85rem;
}
.send:hover {
  background: #0891b2;
}
.send:disabled {
  opacity: 0.5;
  cursor: default;
}
.err {
  color: #ef4444;
  font-size: 0.82rem;
  margin-top: 12px;
}
.resp {
  margin-top: 16px;
}
.status-line {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 8px;
}
.code {
  font-weight: 700;
  color: #ef4444;
}
.code.ok {
  color: #34d399;
}
.time {
  color: #94a3b8;
  font-size: 0.8rem;
}
@media (max-width: 700px) {
  .console-view {
    grid-template-columns: 1fr;
  }
}
</style>
