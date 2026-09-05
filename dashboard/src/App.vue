<script setup lang="ts">
import { defineAsyncComponent, ref, onMounted } from 'vue'
import ConsoleLayout from './layouts/ConsoleLayout.vue'
import { ensureDeviceMetaLoaded } from './deviceMeta'
import { refreshAll } from './usePoll'

const DashboardView = defineAsyncComponent(() => import('./views/DashboardView.vue'))
const OntologyLabView = defineAsyncComponent(() => import('./views/OntologyLabView.vue'))
const ApiConsoleView = defineAsyncComponent(() => import('./views/ApiConsoleView.vue'))
const DeviceManagerView = defineAsyncComponent(() => import('./views/DeviceManagerView.vue'))
const SystemStatusView = defineAsyncComponent(() => import('./views/SystemStatusView.vue'))
const WallboardView = defineAsyncComponent(() => import('./views/WallboardView.vue'))

const active = ref('monitor')
const refreshKey = ref(0)

const wall = ref(
  new URLSearchParams(location.search).get('wall') === '1' ||
    location.hash === '#wall',
)

const VIEWS: Record<string, unknown> = {
  monitor: DashboardView,
  lab: OntologyLabView,
  console: ApiConsoleView,
  devices: DeviceManagerView,
  system: SystemStatusView,
}

function exitWall() {
  wall.value = false
  history.replaceState(null, '', location.pathname)
}

onMounted(() => {
  ensureDeviceMetaLoaded()
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && wall.value) exitWall()
  })
})
</script>

<template>
  <WallboardView v-if="wall" @exit="exitWall" />
  <ConsoleLayout v-else v-model:active="active" @refresh="refreshKey++">
    <component :is="VIEWS[active]" :key="`${active}-${refreshKey}`" />
  </ConsoleLayout>
</template>
