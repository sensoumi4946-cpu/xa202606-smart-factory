<script setup lang="ts">
import { defineAsyncComponent, ref, onMounted } from 'vue';
import ConsoleLayout from './layouts/ConsoleLayout.vue';
import { ensureDeviceMetaLoaded } from './deviceMeta';
import { refreshAll } from './usePoll';
import { clearBrowserSession, createBrowserSession, hasBrowserSession } from './api';
const credential = ref('');
const authenticated = ref(false);
async function connect() {
    const accepted = await createBrowserSession(credential.value);
    if (!accepted) {
        authError.value = '连接失败，请检查访问密钥和服务状态';
        return;
    }
    credential.value = '';
    authenticated.value = true;
    refreshAll();
    ensureDeviceMetaLoaded();
}
const authError = ref('');
const DashboardView = defineAsyncComponent(() => import('./views/DashboardView.vue'));
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
    console: ApiConsoleView,
    devices: DeviceManagerView,
    system: SystemStatusView,
};
function exitWall() {
    wall.value = false;
    history.replaceState(null, '', location.pathname);
}
async function logout() {
    await clearBrowserSession();
    authenticated.value = false;
    credential.value = '';
}
onMounted(async () => {
    sessionStorage.removeItem('factory-api-key');
    authenticated.value = await hasBrowserSession().catch(() => false);
    if (authenticated.value)
        ensureDeviceMetaLoaded();
    window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && wall.value)
            exitWall();
    });
});
</script>

<template>
  <main v-if="!authenticated" class="login-page">
    <form
      class="login-card"
      @submit.prevent="connect().catch(() => authError = '无法连接服务')"
    >
      <div class="login-brand">XA-202606</div>
      <h1>智慧工厂安全监控平台</h1>
      <p>请输入访问密钥连接平台</p>

      <label for="access-key">访问密钥</label>
      <input
        id="access-key"
        v-model="credential"
        type="password"
        autocomplete="off"
        placeholder="输入访问密钥"
      />
      <button type="submit">进入平台</button>
      <p v-if="authError" class="login-error" role="alert">
        {{ authError }}
      </p>
    </form>
  </main>

  <WallboardView v-else-if="wall" @exit="exitWall" />
  <ConsoleLayout
    v-else
    v-model:active="active"
    @refresh="refreshKey++"
    @logout="logout"
  >
    <component
      :is="VIEWS[active]"
      :key="`${active}-${refreshKey}`"
    />
  </ConsoleLayout>
</template>
<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background: #14181b;
}

.login-card {
  width: min(100%, 420px);
  padding: 36px;
  background: #1c2125;
  border: 1px solid #384047;
  border-radius: 8px;
}

.login-brand {
  color: #d6a24b;
  font: 700 13px var(--font-mono);
  letter-spacing: .1em;
}

.login-card h1 {
  margin: 12px 0 6px;
  font-size: 24px;
  color: #f0f2f3;
}

.login-card p {
  color: #929ca4;
  font-size: 13px;
}

.login-card label {
  display: block;
  margin: 26px 0 8px;
  color: #c2c8cd;
  font-size: 13px;
}

.login-card input {
  width: 100%;
  height: 44px;
  padding: 0 12px;
  color: #f0f2f3;
  background: #14181b;
  border: 1px solid #4a545d;
  border-radius: 5px;
  font: inherit;
}

.login-card input:focus {
  outline: 2px solid #d6a24b;
  outline-offset: 1px;
}

.login-card button {
  width: 100%;
  height: 44px;
  margin-top: 16px;
  color: #14181b;
  background: #d6a24b;
  border: 0;
  border-radius: 5px;
  font-weight: 700;
  cursor: pointer;
}

.login-card .login-error {
  color: #f04444;
}
</style>