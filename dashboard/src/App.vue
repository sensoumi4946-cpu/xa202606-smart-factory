<script setup lang="ts">
// Root component: hosts ConsoleLayout and renders the active tab's view.
// The refresh button in the layout bumps a key that force-remounts the
// current view so it re-fetches on demand.
import { ref } from 'vue'
import ConsoleLayout from './layouts/ConsoleLayout.vue'
import DashboardView from './views/DashboardView.vue'
import ApiConsoleView from './views/ApiConsoleView.vue'
import DeviceManagerView from './views/DeviceManagerView.vue'
import SystemStatusView from './views/SystemStatusView.vue'

const active = ref('monitor')
const refreshKey = ref(0)

const VIEWS: Record<string, unknown> = {
  monitor: DashboardView,
  console: ApiConsoleView,
  devices: DeviceManagerView,
  system: SystemStatusView,
}
</script>

<template>
  <ConsoleLayout v-model:active="active" @refresh="refreshKey++">
    <component :is="VIEWS[active]" :key="`${active}-${refreshKey}`" />
  </ConsoleLayout>
</template>

<style>
body {
  margin: 0;
  font-family: 'Segoe UI', system-ui, sans-serif;
  background: #0f172a;
  color: #e2e8f0;
}
</style>
