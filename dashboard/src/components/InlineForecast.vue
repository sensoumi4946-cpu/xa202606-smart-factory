<script setup lang="ts">
import { computed } from 'vue'
import { rawRequest } from '../api'
import { usePoll } from '../usePoll'

type ForecastState = 'breached' | 'predicted_breach' | 'watch' | 'stable'

interface ForecastItem {
  device_id: string
  property_name: string
  current_value: number
  predicted_value: number
  predicted_ci_95: [number, number]
  threshold: number
  state: ForecastState
  model_quality?: 'reliable' | 'low_confidence' | 'insufficient_data'
  backtest_evaluated?: number
}

interface ForecastStatus {
  items: ForecastItem[]
}

const props = defineProps<{
  deviceId: string
  properties: string[]
}>()

async function fetchForecast(): Promise<ForecastStatus> {
  const response = await rawRequest(
    'GET',
    '/analytics/api/v1/forecast-status?horizon_minutes=10',
  )
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.body as ForecastStatus
}

const { data, error } = usePoll<ForecastStatus>(
  'forecast-status:10m',
  fetchForecast,
  5000,
)

const rank: Record<ForecastState, number> = {
  breached: 4,
  predicted_breach: 3,
  watch: 2,
  stable: 1,
}

const item = computed(() =>
  (data.value?.items ?? [])
    .filter(
      (entry) =>
        entry.device_id === props.deviceId &&
        props.properties.includes(entry.property_name),
    )
    .sort((a, b) => rank[b.state] - rank[a.state])[0],
)

const propertyLabel: Record<string, string> = {
  temperature: '温度',
  humidity: '湿度',
  distance: 'AGV 距离',
  co: '一氧化碳',
  smoke: '烟雾',
  combustible_gas: '可燃气体',
}

const stateLabel: Record<ForecastState, string> = {
  breached: '当前越界',
  predicted_breach: '预计越界',
  watch: '趋势关注',
  stable: '趋势稳定',
}

const qualityLabel = {
  reliable: '模型可靠',
  low_confidence: '低可信度',
  insufficient_data: '验证中',
}

const actionLabel: Record<ForecastState, string> = {
  breached: '执行现有安全策略并确认告警',
  predicted_breach: '提前检查设备并准备安全策略',
  watch: '提高监测频率并安排现场检查',
  stable: '继续监测',
}

function number(value: number): string {
  return Number.isFinite(value) ? value.toFixed(1) : '--'
}
</script>

<template>
  <div class="forecast" :class="item?.state">
    <div v-if="error" class="unavailable">趋势预测暂不可用</div>
    <div v-else-if="!item" class="unavailable">预测样本积累中</div>

    <template v-else>
      <div class="forecast-head">
        <strong>10 分钟预测 · {{ propertyLabel[item.property_name] ?? item.property_name }}</strong>
        <span class="state">{{ stateLabel[item.state] }}</span>
      </div>

      <div class="values mono">
        <span>当前 <b>{{ number(item.current_value) }}</b></span>
        <span class="arrow">→</span>
        <span>预测 <b>{{ number(item.predicted_value) }}</b></span>
        <span>阈值 <b>{{ number(item.threshold) }}</b></span>
      </div>

      <div class="interval mono">
        95% 区间 {{ number(item.predicted_ci_95[0]) }}–{{ number(item.predicted_ci_95[1]) }}
      </div>

      <div
        class="quality"
        :class="item.model_quality ?? 'insufficient_data'"
      >
        {{ qualityLabel[item.model_quality ?? 'insufficient_data'] }}
        · 回测 n={{ item.backtest_evaluated ?? 0 }}
      </div>

      <div v-if="item.state !== 'stable'" class="action">
        {{ actionLabel[item.state] }}
      </div>
    </template>
  </div>
</template>

<style scoped>
.forecast {
  margin-top: 8px;
  padding: 7px 9px;
  border: 1px solid var(--line);
  border-left: 3px solid var(--ok);
  background: var(--surface-2);
  min-width: 0;
}
.forecast.watch { border-left-color: var(--warn); }
.forecast.breached,
.forecast.predicted_breach { border-left-color: var(--danger); }

.forecast-head,
.values {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 7px;
}
.forecast-head strong { color: var(--text); font-size: 11px; }
.state { color: var(--ok); font-size: 10px; white-space: nowrap; }
.watch .state { color: var(--warn); }
.breached .state,
.predicted_breach .state { color: var(--danger); }

.values {
  justify-content: flex-start;
  flex-wrap: wrap;
  margin-top: 5px;
  font-size: 10px;
  color: var(--text-faint);
}
.values b { color: var(--text); }
.arrow { color: var(--semantic); }

.interval {
  margin-top: 4px;
  color: var(--text-faint);
  font-size: 9px;
}
.quality {
  margin-top: 4px;
  color: var(--text-faint);
  font-size: 9px;
}
.quality.reliable { color: var(--ok); }
.quality.low_confidence { color: var(--warn); }
.quality.insufficient_data { color: var(--text-faint); }

.action {
  margin-top: 5px;
  padding-top: 5px;
  border-top: 1px solid var(--line);
  color: var(--warn);
  font-size: 10px;
}
.breached .action,
.predicted_breach .action { color: var(--danger); }
.unavailable { color: var(--text-faint); font-size: 10px; }
</style>
