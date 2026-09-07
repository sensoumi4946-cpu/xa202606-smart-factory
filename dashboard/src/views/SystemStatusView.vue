<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { rawRequest, fetchSystemStatus, type SystemStatus } from '../api'
import { useClock, ageMs, ageLabel } from '../freshness'

interface Decision {
  decision_id: string
  policy_name: string
  label_zh: string
  hazard_rule: string
  target_device: string
  action: string
  severity: string
  outcome: string
  ontology_version: string
  decided_at: string
  subsystems: string[]
  protocols: string[]
  causal_chain: string[]
  explanation_zh: string
  fingerprint: string
  occurrence_count: number
  last_triggered_at: string
}

const status = ref<SystemStatus | null>(null)
const decisions = ref<Decision[]>([])
const decisionTotal = ref(0)
const totalOccurrences = ref(0)
const chain = ref<{ valid: boolean; entries: number } | null>(null)
const certificate = ref<Record<string, unknown> | null>(null)
const selected = ref<string | null>(null)
const clock = useClock()
let timer: ReturnType<typeof setInterval> | undefined

async function get(path: string): Promise<unknown> {
  try {
    const res = await rawRequest('GET', path)
    return res.ok ? res.body : null
  } catch {
    return null
  }
}

async function load() {
  try {
    status.value = await fetchSystemStatus()
  } catch {
    status.value = null
  }
  const d = (await get('/api/v1/decisions?limit=40')) as {
    items?: Decision[]
    total?: number
    total_occurrences?: number
  } | null
  decisions.value = d?.items ?? []
  decisionTotal.value = d?.total ?? 0
  totalOccurrences.value = d?.total_occurrences ?? 0
  chain.value = (await get('/api/v1/security/audit/verify')) as typeof chain.value
  certificate.value = (await get('/api/v1/safety')) as Record<string, unknown> | null
}

const detail = computed(
  () => decisions.value.find((d) => d.decision_id === selected.value) ?? null,
)

function timeOf(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? '--'
    : d.toLocaleTimeString('zh-CN', { hour12: false })
}

function relOf(iso: string): string {
  return ageLabel(ageMs(iso, clock.value))
}

function outcomeLabel(outcome: string): string {
  if (outcome === 'pending') return '已生成 · 等待设备确认'
  if (outcome === 'dispatched') return '已发布 · 等待设备确认'
  if (outcome === 'acked' || outcome === 'executed') return '设备已确认'
  if (outcome === 'failed' || outcome === 'dispatch_failed') return '处理失败'
  return outcome
}

onMounted(() => {
  load()
  timer = setInterval(load, 4000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="page">
    <section class="ledger">
      <header class="lhead">
        <div>
          <h1>自主决策台账</h1>
          <p>平台根据语义规则自动生成安全决策；物理执行须由设备确认。</p>
        </div>
        <div class="ledger-counts">
          <span>决策事件 <b class="mono">{{ decisionTotal }}</b></span>
          <span>持续触发 <b class="mono">{{ totalOccurrences }}</b></span>
        </div>
      </header>

      <div class="split">
        <table class="rows">
          <thead>
            <tr>
              <th class="c-time">时间</th>
              <th>判定</th>
              <th class="c-dev">目标对象</th>
              <th class="c-act">建议动作</th>
              <th class="c-count">持续触发</th>
              <th class="c-src">证据协议</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="d in decisions"
              :key="d.decision_id"
              :class="{ sel: selected === d.decision_id, crit: d.severity === 'critical' }"
              @click="selected = d.decision_id"
            >
              <td class="c-time mono">{{ timeOf(d.decided_at) }}</td>
              <td>{{ d.label_zh }}</td>
              <td class="c-dev mono">{{ d.target_device }}</td>
              <td class="c-act mono">{{ d.action }}</td>
              <td class="c-count mono">×{{ d.occurrence_count ?? 1 }}</td>
              <td class="c-src mono">
                {{ d.protocols.map((p) => p.toUpperCase()).join('+') }}
              </td>
            </tr>
            <tr v-if="!decisions.length">
              <td colspan="6" class="empty">
                暂无自主决策记录。触发跨子系统风险后，此处会记录决策及其证据。
              </td>
            </tr>
          </tbody>
        </table>

        <aside class="detail">
          <template v-if="detail">
            <h2>{{ detail.label_zh }}</h2>
            <p class="rule mono">{{ detail.hazard_rule }} · {{ detail.severity }}</p>
            <p class="why">{{ detail.explanation_zh }}</p>
            <ol class="chain">
              <li v-for="(c, i) in detail.causal_chain" :key="i" class="mono">{{ c }}</li>
            </ol>
            <dl class="meta">
              <dt>本体版本</dt><dd class="mono">{{ detail.ontology_version }}</dd>
              <dt>决策状态</dt><dd>{{ outcomeLabel(detail.outcome) }}</dd>
              <dt>持续触发</dt><dd class="mono">×{{ detail.occurrence_count ?? 1 }}</dd>
              <dt>记录指纹</dt><dd class="mono trunc">{{ detail.fingerprint }}</dd>
              <dt>首次判定</dt><dd>{{ relOf(detail.decided_at) }}</dd>
              <dt>最近触发</dt><dd>{{ relOf(detail.last_triggered_at || detail.decided_at) }}</dd>
            </dl>
          </template>
          <p v-else class="placeholder">选择左侧任一条记录，查看其因果链与审计信息。</p>
        </aside>
      </div>
    </section>

    <footer class="strip">
      <div class="cell">
        <span class="k">后端</span>
        <span class="v" :class="status?.healthOk ? 'ok' : 'bad'">
          {{ status?.healthOk ? '正常' : '异常' }}
        </span>
      </div>
      <div class="cell">
        <span class="k">Fuseki</span>
        <span class="v" :class="status?.fusekiOk ? 'ok' : 'bad'">
          {{ status?.fusekiOk ? '在线' : '离线' }}
        </span>
      </div>
      <div class="cell">
        <span class="k">已注册设备</span>
        <span class="v mono">{{ status?.deviceCount ?? '--' }}</span>
      </div>
      <div class="cell">
        <span class="k">近 10 分钟报文</span>
        <span class="v mono">{{ status?.recentCount ?? '--' }}</span>
      </div>
      <div class="cell">
        <span class="k">累计告警</span>
        <span class="v mono">{{ status?.alertTotal ?? '--' }}</span>
      </div>
      <div class="cell">
        <span class="k">审计链</span>
        <span class="v" :class="chain?.valid ? 'ok' : 'bad'">
          {{ chain === null ? '--' : chain.valid ? `完整 (${chain.entries})` : '已被篡改' }}
        </span>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 0;
}
.ledger { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.lhead {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  border-bottom: 1px solid var(--line);
  padding-bottom: 8px;
}
.ledger-counts { display: flex; gap: 14px; color: var(--text-faint); font-size: 11px; }
.ledger-counts b { color: var(--text); }
h1 { margin: 0; font-size: 15px; font-weight: 600; }
.lhead p { margin: 3px 0 0; font-size: 11px; color: var(--text-faint); }

.split {
  display: grid;
  grid-template-columns: 1.7fr 1fr;
  gap: 14px;
  flex: 1;
  min-height: 0;
  padding-top: 10px;
  overflow: auto;
}

.rows { width: 100%; border-collapse: collapse; font-size: 12px; align-self: start; }
.rows th {
  text-align: left;
  font-weight: 500;
  font-size: 11px;
  color: var(--text-faint);
  padding: 5px 8px;
  border-bottom: 1px solid var(--line);
}
.rows td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--line);
  color: var(--text-dim);
}
.rows tr { cursor: pointer; }
.rows tr:hover td { background: var(--surface-2); }
.rows tr.sel td { background: var(--surface-2); color: var(--text); }
.rows tr.crit td:nth-child(2) { color: var(--danger); }
.c-time { width: 76px; }
.c-dev { width: 140px; }
.c-act { width: 72px; }
.c-count { width: 78px; white-space: nowrap; color: var(--warn) !important; }
.c-src { width: 110px; }
.empty { color: var(--text-faint); padding: 20px 8px; }

.detail {
  background: var(--surface);
  border: 1px solid var(--line);
  padding: 12px 14px;
  font-size: 12px;
  align-self: start;
}
.detail h2 { margin: 0 0 2px; font-size: 13px; }
.rule { margin: 0 0 8px; font-size: 11px; color: var(--text-faint); }
.why { margin: 0 0 10px; line-height: 1.7; color: var(--text-dim); }
.chain { margin: 0 0 10px; padding-left: 18px; }
.chain li { font-size: 11px; color: var(--text-faint); line-height: 1.8; }
.meta { display: grid; grid-template-columns: auto 1fr; gap: 3px 12px; margin: 0; }
.meta dt { color: var(--text-faint); font-size: 11px; }
.meta dd { margin: 0; font-size: 11px; color: var(--text-dim); }
.trunc { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.placeholder { color: var(--text-faint); margin: 0; }

.strip {
  display: flex;
  flex-wrap: wrap;
  gap: 0;
  border-top: 1px solid var(--line);
  margin-top: 12px;
  flex-shrink: 0;
  background: var(--surface);
}
.cell {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 8px 16px;
  border-right: 1px solid var(--line);
  font-size: 11px;
}
.k { color: var(--text-faint); }
.v { color: var(--text-dim); }
.v.ok { color: var(--ok); }
.v.bad { color: var(--danger); }
</style>
