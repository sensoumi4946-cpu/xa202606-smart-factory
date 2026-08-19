<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    label: string
    value: number | null
    unit?: string
    min?: number
    max?: number
    warn?: number
    danger?: number
    /** 'high' = big values are bad (CO). 'low' = small values are bad (distance). */
    direction?: 'high' | 'low'
    size?: number
  }>(),
  {
    unit: '',
    min: 0,
    max: 100,
    direction: 'high',
    size: 150,
  },
)

const R = 54
const CIRC = Math.PI * R
const SWEEP = 240
const START = 150

function clamp(v: number, lo: number, hi: number) {
  return Math.min(hi, Math.max(lo, v))
}

const pct = computed(() => {
  if (props.value === null || props.max === props.min) return 0
  return clamp((props.value - props.min) / (props.max - props.min), 0, 1)
})

const angle = computed(() => START + pct.value * SWEEP)

function polar(deg: number, r: number) {
  const rad = (deg * Math.PI) / 180
  return { x: 80 + r * Math.cos(rad), y: 80 + r * Math.sin(rad) }
}

function arcPath(fromDeg: number, toDeg: number, r: number) {
  const a = polar(fromDeg, r)
  const b = polar(toDeg, r)
  const large = toDeg - fromDeg > 180 ? 1 : 0
  return `M ${a.x} ${a.y} A ${r} ${r} 0 ${large} 1 ${b.x} ${b.y}`
}

const trackPath = computed(() => arcPath(START, START + SWEEP, R))

const valuePath = computed(() => {
  if (pct.value <= 0.001) return ''
  return arcPath(START, angle.value, R)
})

function degForValue(v: number) {
  return START + clamp((v - props.min) / (props.max - props.min), 0, 1) * SWEEP
}

const warnBand = computed(() => {
  if (props.warn === undefined) return ''
  return props.direction === 'high'
    ? arcPath(degForValue(props.warn), START + SWEEP, R + 11)
    : arcPath(START, degForValue(props.warn), R + 11)
})

const dangerBand = computed(() => {
  if (props.danger === undefined) return ''
  return props.direction === 'high'
    ? arcPath(degForValue(props.danger), START + SWEEP, R + 11)
    : arcPath(START, degForValue(props.danger), R + 11)
})

const level = computed(() => {
  if (props.value === null) return 'none'
  const v = props.value
  if (props.direction === 'high') {
    if (props.danger !== undefined && v >= props.danger) return 'danger'
    if (props.warn !== undefined && v >= props.warn) return 'warn'
  } else {
    if (props.danger !== undefined && v <= props.danger) return 'danger'
    if (props.warn !== undefined && v <= props.warn) return 'warn'
  }
  return 'ok'
})

const display = computed(() =>
  props.value === null ? '--' : Math.abs(props.value) >= 100
    ? props.value.toFixed(0)
    : props.value.toFixed(1),
)

const needle = computed(() => polar(angle.value, R - 8))
</script>

<template>
  <div class="gauge" :style="{ width: size + 'px' }">
    <svg viewBox="0 0 160 130" :width="size" :height="size * 0.82">
      <path :d="trackPath" class="track" />
      <path v-if="warnBand" :d="warnBand" class="band warn" />
      <path v-if="dangerBand" :d="dangerBand" class="band danger" />
      <path v-if="valuePath" :d="valuePath" class="value" :class="level" />
      <line
        v-if="props.value !== null"
        x1="80"
        y1="80"
        :x2="needle.x"
        :y2="needle.y"
        class="needle"
        :class="level"
      />
      <circle cx="80" cy="80" r="4" class="hub" />
      <text x="80" y="70" class="num" :class="level">{{ display }}</text>
      <text x="80" y="86" class="unit">{{ unit }}</text>
    </svg>
    <div class="label">{{ label }}</div>
  </div>
</template>

<style scoped>
.gauge {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.track {
  fill: none;
  stroke: #1e293b;
  stroke-width: 9;
  stroke-linecap: round;
}
.band {
  fill: none;
  stroke-width: 3;
  stroke-linecap: round;
  opacity: 0.55;
}
.band.warn { stroke: #fbbf24; }
.band.danger { stroke: #ef4444; }
.value {
  fill: none;
  stroke-width: 9;
  stroke-linecap: round;
  stroke: #38bdf8;
  transition: stroke 0.3s ease;
}
.value.warn { stroke: #fbbf24; }
.value.danger { stroke: #ef4444; }
.needle {
  stroke: #e2e8f0;
  stroke-width: 2;
  stroke-linecap: round;
  transition: all 0.5s cubic-bezier(0.34, 1.3, 0.64, 1);
}
.needle.warn { stroke: #fbbf24; }
.needle.danger { stroke: #ef4444; }
.hub { fill: #94a3b8; }
.num {
  text-anchor: middle;
  font-family: 'JetBrains Mono', monospace;
  font-size: 21px;
  font-weight: 700;
  fill: #7dd3fc;
}
.num.warn { fill: #fbbf24; }
.num.danger { fill: #fca5a5; }
.unit {
  text-anchor: middle;
  font-size: 9px;
  fill: #64748b;
}
.label {
  font-size: 0.76rem;
  color: #94a3b8;
  text-align: center;
}
</style>
