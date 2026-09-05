<script setup lang="ts">
import { ref } from 'vue'
import { runSemanticView, runSparqlQuery, type SparqlResult } from '../api'

const PREFIX =
  'PREFIX sosa: <http://www.w3.org/ns/sosa/>\nPREFIX sf: <http://example.org/smart-factory#>\n\n'

function baseQuery(filter: string): string {
  return (
    PREFIX +
    'SELECT DISTINCT ?sensor ?subsystem ?protocol ?prop WHERE {\n' +
    '  ?obs a sosa:Observation ;\n' +
    '       sosa:madeBySensor ?sensor ;\n' +
    '       sosa:observedProperty ?prop .\n' +
    '  OPTIONAL { ?sensor sf:belongsToSubsystem ?subsystem }\n' +
    '  OPTIONAL { ?sensor sf:transportedVia ?protocol }\n' +
    (filter ? filter + '\n' : '') +
    '} ORDER BY ?sensor ?prop'
  )
}

const PRESETS: Array<{ view: string; label: string; sparql: string }> = [
  {
    view: 'sensor-observations',
    label: '全部传感器',
    sparql: baseQuery(''),
  },
  {
    view: 'co-temp-sensors',
    label: 'CO + 温度 (火灾关联)',
    sparql: baseQuery(
      '  { SELECT DISTINCT ?sensor WHERE {\n' +
        '      ?fo sosa:madeBySensor ?sensor ; sosa:observedProperty ?fp .\n' +
        '      VALUES ?fp { sf:measuresCO sf:measuresTemperature } } }',
    ),
  },
  {
    view: 'fire-risk-sensors',
    label: '消防安全传感器',
    sparql: baseQuery(
      '  VALUES ?prop { sf:measuresTemperature sf:measuresCO\n' +
        '                 sf:measuresSmoke sf:measuresCombustibleGas }',
    ),
  },
  {
    view: 'gas-subsystem-detail',
    label: '气体子系统',
    sparql: baseQuery(
      '  ?sensor sf:belongsToSubsystem sf:GasMonitoringSubsystem .\n' +
        '  BIND(sf:GasMonitoringSubsystem AS ?subsystem)',
    ),
  },
  {
    view: 'production-sensors',
    label: '生产线传感器',
    sparql: baseQuery(
      '  VALUES ?prop { sf:measuresDistance sf:measuresCount\n' +
        '                 sf:measuresOccupancy sf:measuresLightState }',
    ),
  },
]

const activePreset = ref(0)
const queryText = ref(PRESETS[0].sparql)
const edited = ref(false)
const running = ref(false)
const error = ref('')
const result = ref<SparqlResult | null>(null)

const COLUMN_LABELS: Record<string, string> = {
  sensor: '传感器',
  subsystem: '子系统',
  observes: '观测属性',
  protocol: '通信协议',
  prop: '观测属性',
  value: '数值',
  unit: '单位',
  timestamp: '时间',
}

function pickPreset(i: number) {
  activePreset.value = i
  queryText.value = PRESETS[i].sparql
  edited.value = false
  error.value = ''
}

function onEdit() {
  edited.value = queryText.value !== PRESETS[activePreset.value].sparql
}

async function run() {
  running.value = true
  error.value = ''
  try {
    result.value = edited.value
      ? await runSparqlQuery(queryText.value)
      : await runSemanticView(PRESETS[activePreset.value].view)
  } catch (e) {
    result.value = null
    error.value =
      e instanceof Error && e.message === 'ENDPOINT_MISSING'
        ? '自定义查询需要后端 POST /api/v1/semantic/query 端点 (语义网关分支待合并)。预设查询仍可运行。'
        : '查询失败 — 语义服务不可用'
  } finally {
    running.value = false
  }
}
</script>

<template>
  <div class="panel">
    <header class="head">
      <h3>SPARQL 查询</h3>
      <span class="sub mono">Apache Jena Fuseki :3030</span>
    </header>

    <div class="presets" role="tablist">
      <button
        v-for="(p, i) in PRESETS"
        :key="p.view"
        class="chip"
        :class="{ active: activePreset === i && !edited }"
        role="tab"
        @click="pickPreset(i)"
      >
        {{ p.label }}
      </button>
    </div>

    <textarea
      v-model="queryText"
      class="editor mono"
      rows="9"
      spellcheck="false"
      aria-label="SPARQL 查询语句"
      @input="onEdit"
    ></textarea>

    <div class="actions">
      <span v-if="edited" class="hint">已修改 — 将作为自定义查询发送</span>
      <button class="run" :disabled="running" @click="run">
        {{ running ? '运行中…' : '运行查询' }}
      </button>
    </div>

    <div v-if="error" class="err">{{ error }}</div>

    <div v-if="result" class="results">
      <table>
        <thead>
          <tr>
            <th v-for="c in result.columns" :key="c">{{ COLUMN_LABELS[c] ?? c }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in result.rows" :key="i">
            <td v-for="c in result.columns" :key="c" class="mono">
              {{ r[c] }}
            </td>
          </tr>
          <tr v-if="!result.rows.length">
            <td :colspan="result.columns.length" class="empty">
              查询无结果
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.panel {
  padding: var(--pad);
}
.head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 10px;
}
h3 {
  margin: 0;
  font-size: var(--fs-md);
  color: var(--semantic);
}
.sub {
  font-size: var(--fs-xs);
  color: var(--text-faint);
  letter-spacing: 0.08em;
}
.presets {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.chip {
  background: var(--surface-2);
  color: var(--text-dim);
  border: 1px solid var(--line-strong);
  border-radius: 999px;
  padding: 4px 12px;
  font-size: var(--fs-xs);
  font-family: var(--font-ui);
  cursor: pointer;
}
.chip:hover {
  color: var(--text);
}
.chip.active {
  color: var(--semantic);
  border-color: var(--semantic);
  background: var(--semantic-bg);
}
.chip:focus-visible,
.run:focus-visible {
  outline: 2px solid var(--semantic);
  outline-offset: 2px;
}
.editor {
  width: 100%;
  box-sizing: border-box;
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  font-size: var(--fs-xs);
  line-height: 1.55;
  resize: vertical;
}
.editor:focus {
  outline: none;
  border-color: var(--semantic);
}
.actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 8px;
}
.hint {
  font-size: var(--fs-xs);
  color: var(--warn);
}
.run {
  background: var(--semantic-bg);
  color: var(--semantic);
  border: 1px solid var(--semantic);
  border-radius: var(--radius-sm);
  padding: 6px 18px;
  font-size: var(--fs-sm);
  font-family: var(--font-ui);
  font-weight: 600;
  cursor: pointer;
}
.run:disabled {
  opacity: 0.5;
  cursor: wait;
}
.err {
  margin-top: 10px;
  color: var(--danger);
  font-size: var(--fs-sm);
}
.results {
  margin-top: 12px;
  max-height: 260px;
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--fs-sm);
}
th,
td {
  padding: 6px 10px;
  text-align: left;
  border-bottom: 1px solid var(--line);
}
th {
  color: var(--text-dim);
  font-weight: 600;
  position: sticky;
  top: 0;
  background: var(--surface);
}
td {
  color: var(--text);
  font-size: var(--fs-xs);
}
.empty {
  color: var(--text-faint);
  text-align: center;
  padding: 14px;
}
</style>
