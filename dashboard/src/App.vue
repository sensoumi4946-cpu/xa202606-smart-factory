<script setup lang="ts">
import { defineAsyncComponent, ref, onMounted } from 'vue';
import ConsoleLayout from './layouts/ConsoleLayout.vue';
import { ensureDeviceMetaLoaded } from './deviceMeta';
import { refreshAll } from './usePoll';
import { getApiKey, setApiKey } from './api';
const credential = ref(getApiKey());
const authenticated = ref(Boolean(credential.value));
async function connect() {
    const response = await fetch('/api/v1/devices', { headers: { 'X-API-Key': credential.value } });
    if (!response.ok) {
        authError.value = '连接失败，请检查访问密钥和服务状态';
        return;
    }
    setApiKey(credential.value);
    authenticated.value = true;
    refreshAll();
    ensureDeviceMetaLoaded();
}
const authError = ref('');
const DashboardView = defineAsyncComponent(() => import('./views/DashboardView.vue'));
const OntologyLabView = defineAsyncComponent(() => import('./views/OntologyLabView.vue'));
const ApiConsoleView = defineAsyncComponent(() => import('./views/ApiConsoleView.vue'));
const DeviceManagerView = defineAsyncComponent(() => import('./views/DeviceManagerView.vue'));
const SystemStatusView = defineAsyncComponent(() => import('./views/SystemStatusView.vue'));
const WallboardView = defineAsyncComponent(() => import('./views/WallboardView.vue'));
const active = ref('monitor');
const refreshKey = ref(0);
const wall = ref(new URLSearchParams(location.search).get('wall') === '1' ||
    location.hash === '#wall');
const VIEWS: Record<string, unknown> = {
    monitor: DashboardView,
    lab: OntologyLabView,
    console: ApiConsoleView,
    devices: DeviceManagerView,
    system: SystemStatusView,
};
function exitWall() {
    wall.value = false;
    history.replaceState(null, '', location.pathname);
}
onMounted(() => {
    ensureDeviceMetaLoaded();
    window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && wall.value)
            exitWall();
    });
});
</script>

<template>
  <form v-if="!authenticated" @submit.prevent="connect().catch(() => authError = '无法连接服务')" style="max-width:420px;margin:15vh auto;padding:24px">
    <h1>智慧工厂监控</h1>
    <label for="access-key">访问密钥</label>
    <input id="access-key" v-model="credential" type="password" autocomplete="off" style="display:block;width:100%;margin:16px 0" />
    <button type="submit">连接</button>
    <p role="alert">{{ authError }}</p>
  </form>
  <WallboardView v-else-if="wall" @exit="exitWall" />
  <ConsoleLayout v-else v-model:active="active" @refresh="refreshKey++">
    <component :is="VIEWS[active]" :key="`${active}-${refreshKey}`" />
  </ConsoleLayout>
</template>
