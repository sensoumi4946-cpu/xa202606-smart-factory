<script setup lang="ts">
import { ref } from 'vue'

const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/'
const KEY = import.meta.env.VITE_API_KEY || ''

const PRESETS: Record<string, string> = {
  合法地址: `@prefix sf:  <http://example.org/smart-factory#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

sf:demo_new_sensor a sf:ProtocolBinding ;
    sf:bindsProperty sf:measuresTemperature ;
    sf:transportProtocol "modbus" ;
    sf:deviceId "ESP32_900" ;
    sf:belongsToSubsystem sf:TempHumiditySubsystem ;
    sf:hasUnit "celsius" ;
    sf:registerAddress 40001 ;
    sf:registerBase 40001 ;
    sf:functionCode 3 ;
    sf:registerType "int16" ;
    sf:scaleFactor "0.01"^^xsd:double ;
    sf:pollIntervalMs 2000 .`,

  非法地址: `@prefix sf:  <http://example.org/smart-factory#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

sf:demo_bad_address a sf:ProtocolBinding ;
    sf:bindsProperty sf:measuresTemperature ;
    sf:transportProtocol "modbus" ;
    sf:deviceId "ESP32_901" ;
    sf:belongsToSubsystem sf:TempHumiditySubsystem ;
    sf:hasUnit "celsius" ;
    sf:registerBase 40001 ;
    sf:functionCode 99 ;
    sf:registerType "int16" ;
    sf:scaleFactor "0.01"^^xsd:double ;
    sf:pollIntervalMs 2000 .`,

  类型不一致: `@prefix sf:  <http://example.org/smart-factory#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

sf:demo_bad_type a sf:ProtocolBinding ;
    sf:bindsProperty sf:measuresTemperature ;
    sf:transportProtocol "modbus" ;
    sf:deviceId "ESP32_903" ;
    sf:belongsToSubsystem sf:TempHumiditySubsystem ;
    sf:hasUnit "celsius" ;
    sf:registerAddress 40001 ;
    sf:registerBase 40001 ;
    sf:functionCode 3 ;
    sf:registerType "int8" ;
    sf:scaleFactor "0.01" ;
    sf:pollIntervalMs "2000" .`,
}

const turtle = ref(PRESETS['合法地址'])
const running = ref(false)
const elapsed = ref<number | null>(null)
const accepted = ref<boolean | null>(null)
const violations = ref<string[]>([])
const generated = ref('')
const bindingsAdded = ref<string[]>([])

async function usePreset(name: string) {
  turtle.value = PRESETS[name]
  accepted.value = null
  violations.value = []
  generated.value = ''
  elapsed.value = null
}

async function validate() {
  running.value = true
  accepted.value = null
  violations.value = []
  generated.value = ''
  const t0 = performance.now()
  try {
    const resp = await fetch(`${BASE}api/v1/innovation/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': KEY },
      body: JSON.stringify({ turtle: turtle.value }),
    })
    const data = await resp.json()
    accepted.value = data.accepted
    violations.value = data.violations ?? []
    bindingsAdded.value = data.bindings_added ?? []
    generated.value = data.generated_source ?? ''
  } catch (e) {
    accepted.value = false
    violations.value = [`请求失败：${e}`]
  } finally {
    elapsed.value = performance.now() - t0
    running.value = false
  }
}
</script>

<template>
  <section class="lab">
    <header>
      <h2>本体绑定实时校验</h2>
      <p>粘贴设备本体描述，平台在加载阶段校验。合法则生成适配代码，非法则拒绝并说明原因。</p>
    </header>

    <div class="presets">
      <button v-for="(_, name) in PRESETS" :key="name" class="preset" @click="usePreset(String(name))">
  {{ name }}
  </button>
      <button class="run" :disabled="running" @click="validate">
        {{ running ? '校验中…' : '校验' }}
      </button>
      <span v-if="elapsed !== null" class="ms mono">{{ elapsed.toFixed(1) }} ms</span>
    </div>

    <div class="split">
      <textarea v-model="turtle" class="editor mono" spellcheck="false"></textarea>

      <div class="out">
        <div v-if="accepted === true" class="verdict pass">
          接受 · 注册 {{ bindingsAdded.length }} 条绑定
        </div>
        <div v-else-if="accepted === false" class="verdict fail">
          拒绝 · {{ violations.length }} 项约束未通过
        </div>
        <div v-else class="verdict idle">等待校验</div>

        <ul v-if="violations.length" class="violations mono">
          <li v-for="v in violations" :key="v">{{ v }}</li>
        </ul>

        <pre v-if="generated" class="code mono">{{ generated }}</pre>
      </div>
    </div>
  </section>
</template>

<style scoped>
.lab { padding: 16px; }
header h2 { margin: 0; font-size: 15px; color: var(--semantic); }
header p { margin: 4px 0 14px; font-size: 12px; color: var(--text-dim); }
.presets { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
.preset, .run {
  background: var(--surface-2); border: 1px solid var(--line);
  color: var(--text-dim); border-radius: 4px; padding: 4px 12px;
  font-size: 12px; cursor: pointer; font-family: var(--font-ui);
}
.run { border-color: var(--semantic); color: var(--semantic); }
.run:disabled { opacity: 0.5; cursor: default; }
.ms { font-size: 12px; color: var(--text-faint); margin-left: auto; }
.split { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr); gap: 14px; }
.editor {
  width: 100%; min-height: 340px; box-sizing: border-box;
  background: var(--bg); border: 1px solid var(--line); border-radius: 5px;
  color: var(--text); font-size: 11px; line-height: 1.6; padding: 10px; resize: vertical;
}
.out { min-width: 0; }
.verdict { font-size: 13px; padding: 8px 12px; border-radius: 5px; border: 1px solid var(--line); }
.verdict.pass { color: var(--ok); border-color: var(--ok); }
.verdict.fail { color: var(--danger); border-color: var(--danger); }
.verdict.idle { color: var(--text-faint); }
.violations { list-style: none; padding: 10px 0 0; margin: 0; }
.violations li { font-size: 11px; color: var(--danger); padding: 2px 0; }
.code {
  margin: 10px 0 0; background: var(--bg); border: 1px solid var(--line);
  border-radius: 5px; padding: 10px; font-size: 11px; line-height: 1.5;
  color: var(--text); max-height: 260px; overflow: auto; white-space: pre;
}
@media (max-width: 900px) { .split { grid-template-columns: minmax(0,1fr); } }
</style>