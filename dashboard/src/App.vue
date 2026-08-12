import { ensureDeviceMetaLoaded } from './deviceMeta'
ensureDeviceMetaLoaded()
<script setup lang="ts">
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

