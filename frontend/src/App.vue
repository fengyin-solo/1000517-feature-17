<template>
  <div class="app-shell">
    <aside class="app-side">
      <h1 class="app-title">轨道交通信号设备检修平台</h1>
      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="app-main">
      <header class="app-head">
        <span class="head-desc">面向轨道交通信号机、转辙机、轨道电路、联锁设备的检修计划、故障处置与验收的一体化检修管理后台。</span>
        <span class="head-user">
          <label class="identity-switch">
            当前岗位
            <select :value="identityIndex" @change="switchIdentity(($event.target as HTMLSelectElement).value)">
              <option v-for="(item, index) in IDENTITIES" :key="`${item.role}-${item.operator}`" :value="index">
                {{ item.role }} · {{ item.operator }}{{ item.zone ? `（${item.zone}）` : '' }}
              </option>
            </select>
          </label>
          <span>{{ store.shiftLabel }}</span>
        </span>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import { IDENTITIES, useSessionStore } from '@/stores/session'

const store = useSessionStore()

const identityIndex = computed(() =>
  IDENTITIES.findIndex(
    (item) =>
      item.role === store.identity.role &&
      item.zone === store.identity.zone &&
      item.operator === store.identity.operator,
  ),
)

function switchIdentity(value: string) {
  const index = Number(value)
  if (IDENTITIES[index]) {
    store.setIdentity(IDENTITIES[index])
  }
}

const navItems = [{ label: "运营概览", path: "/" }, { label: "线路区段", path: "/section" }, { label: "信号机", path: "/signal" }, { label: "转辙机", path: "/switch" }, { label: "轨道电路", path: "/track" }, { label: "联锁设备", path: "/interlock" }, { label: "列车防护", path: "/atp" }, { label: "检修计划", path: "/plan" }, { label: "检修任务", path: "/task" }, { label: "故障登记", path: "/fault" }, { label: "故障处置", path: "/dispose" }, { label: "器材领用", path: "/spare" }, { label: "电气测试", path: "/measure" }, { label: "巡视检查", path: "/patrol" }, { label: "天窗作业", path: "/window" }, { label: "监测报警", path: "/alarm" }, { label: "验收确认", path: "/verify" }, { label: "值班交接", path: "/shift" }, { label: "状态评估", path: "/assess" }]
</script>
