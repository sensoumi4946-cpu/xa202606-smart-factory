<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  fetchAdapterAudit,
  fetchAdapterSource,
  fetchDeviceTriples,
  type AdapterAudit,
  type DeviceTriples,
} from '../api'

const audit = ref<AdapterAudit | null>(null)
const triples = ref<DeviceTriples | null>(null)
const source = ref('')
const activeDevice = ref('')
const activeProtocol = ref('')
const error = ref('')
const loading = ref(true)

const protocols = computed(() => audit.value?.protocols ?? [])
const devices = computed(() => audit.value?.devices ?? [])
const aliasPairs = computed(() => Object.entries(audit.value?.device_aliases ?? {}))

const ratio = computed(() => {
  const a = audit.value
  if (!a || a.transport_plumbing_lines === 0) return null
  return (a.generated_lines_total / a.transport_plumbing_lines).toFixed(2)
})

async function selectDevice(deviceId: string) {
  activeDevice.value = deviceId
  try {
    triples.value = await fetchDeviceTriples(deviceId)
  } catch (e) {
    triples.value = null
    error.value = String(e)
  }
}

async function selectProtocol(protocol: string) {
  activeProtocol.value = protocol
  try {
    source.value = (await fetchAdapterSource(protocol)).source
  } catch (e) {
    source.value = ''
    error.value = String(e)
  }
}

function shortValue(value: string | number | boolean | string[]): string {
  return Array.isArray(value) ? value.join(', ') : String(value)
}

onMounted(async () => {
  try {
    audit.value = await fetchAdapterAudit()
    if (devices.value.length) await selectDevice(devices.value[0])
    if (protocols.value.length) await selectProtocol(protocols.value[0])
  } catch (e) {
    error.value = '无法读取本体适配信息，请确认后端已启动。'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="gap">
    <header class="head">
      <div>
        <h2>本体驱动适配生成</h2>
        <p>寄存器地址、缩放系数、字节序、轮询周期与 OPC UA 节点号全部来自本体三元组。</p>
      </div>
      <div v-if="audit" class="tally mono">
        <span :class="audit.single_source_of_truth ? 'ok' : 'bad'">
          {{ audit.single_source_of_truth ? '单一事实来源' : '存在硬编码常量' }}
        </span>
        <span class="dim">{{ audit.binding_count }} 条绑定</span>
        <span class="dim">{{ audit.generated_lines_total }} 行自动生成</span>
        <span v-if="ratio" class="dim">生成/手写 {{ ratio }}</span>
      </div>
    </header>

    <p v-if="loading" class="state">读取中…</p>
    <p v-else-if="error" class="state bad">{{ error }}</p>

    <div v-else class="split">
      <div class="col">
        <div class="tabs">
          <button
            v-for="d in devices"
            :key="d"
            class="tab"
            :class="{ active: d === activeDevice }"
            @click="selectDevice(d)"
          >
            {{ d }}
          </button>
        </div>

        <p v-if="aliasPairs.length" class="alias mono">
          <span v-for="[alias, canonical] in aliasPairs" :key="alias">
            {{ alias }} → {{ canonical }}
          </span>
        </p>

        <table v-if="triples" class="triples mono">
          <tbody>
            <template v-for="t in triples.triples" :key="t.subject">
              <tr class="subject">
                <td colspan="2">{{ t.subject }}</td>
              </tr>
              <tr
                v-for="(value, key) in t.predicates"
                :key="t.subject + String(key)"
                class="triple"
              >
                <td class="p">sf:{{ key }}</td>
                <td class="o">{{ shortValue(value) }}</td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <div class="col">
        <div class="tabs">
          <button
            v-for="p in protocols"
            :key="p"
            class="tab"
            :class="{ active: p === activeProtocol }"
            @click="selectProtocol(p)"
          >
            {{ p }}
          </button>
        </div>
        <pre class="source mono">{{ source }}</pre>
      </div>
    </div>
  </section>
</template>

<style scoped>
.gap {
  background: var(--surface);
  border: 1px solid var(--semantic);
  border-radius: 8px;
  padding: 16px;
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 12px;
}
.head h2 {
  margin: 0;
  font-size: 15px;
  color: var(--semantic);
}
.head p {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-dim);
}
.tally {
  display: flex;
  gap: 12px;
  font-size: 12px;
  white-space: nowrap;
}
.ok { color: var(--ok); }
.bad { color: var(--danger); }
.dim { color: var(--text-faint); }
.state {
  font-size: 12px;
  color: var(--text-dim);
}
.split {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 16px;
}
.col { min-width: 0; }
.tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.tab {
  background: var(--surface-2);
  border: 1px solid var(--line);
  color: var(--text-dim);
  border-radius: 4px;
  padding: 3px 10px;
  font-size: 12px;
  cursor: pointer;
  font-family: var(--font-ui);
}
.tab.active {
  border-color: var(--semantic);
  color: var(--semantic);
  background: var(--semantic-bg);
}
.alias {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 11px;
  color: var(--text-faint);
  margin: 0 0 8px;
}
.triples {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}
.subject td {
  color: var(--semantic);
  padding: 6px 0 2px;
  border-top: 1px solid var(--line);
}
.triple td {
  padding: 1px 0;
  vertical-align: top;
}
.p {
  color: var(--text-dim);
  width: 45%;
}
.o {
  color: var(--text);
  word-break: break-all;
}
.source {
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 10px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--text);
  max-height: 360px;
  overflow: auto;
  white-space: pre;
  margin: 0;
}
@media (max-width: 900px) {
  .split { grid-template-columns: minmax(0, 1fr); }
}
</style>