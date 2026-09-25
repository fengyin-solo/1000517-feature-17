<template>
  <section class="page" data-module="alarm">
    <header class="page-head">
      <div>
        <h2>监测报警管理</h2>
        <p class="page-desc">
          按岗位分流：值班确认本工区非高等级报警，高等级由调度确认，检修只读；跨工区报警可见但不能改动。
          当前账号：{{ session.operator.name }}（{{ session.operator.role }}<template v-if="session.operator.worksite">·{{ session.operator.worksite }}</template>）
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记报警事件</button>
        <button class="btn" type="button" @click="exportRows">导出监测报警清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card" :class="{ highlight: item.label === '我的待确认' }">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <div class="scope-tabs" role="tablist">
      <button
        v-for="tab in scopeTabs"
        :key="tab.value"
        type="button"
        class="scope-tab"
        :class="{ active: scope === tab.value }"
        @click="switchScope(tab.value)"
      >
        {{ tab.label }}<span v-if="tab.value === 'mine'" class="scope-badge">{{ statsMap['我的待确认'] }}</span>
      </button>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>报警编号</span>
        <input v-model="keyword" placeholder="按报警编号检索" />
      </label>
      <label class="filter-item">
        <span>报警状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>归属</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :class="{ 'cross-row': row['跨工区'] }">
          <td v-for="column in columns" :key="column">
            <span v-if="column === '报警等级'" class="level-tag" :class="levelClass(row['报警等级'])">{{ row[column] ?? '—' }}</span>
            <span v-else>{{ row[column] ?? '—' }}</span>
          </td>
          <td>
            <span v-if="row['我的报警']" class="mine-tag">我的</span>
            <span v-else-if="row['跨工区']" class="cross-tag">跨工区·只读</span>
            <span v-else class="muted-tag">非我负责</span>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="!can(row, action)"
              :title="reason(row, action)"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">当前条件下暂无监测报警数据</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条监测报警记录</span>
      <span v-if="message" :class="messageOk ? 'ok-text' : 'error-text'">{{ message }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { request } from '@/api/client'
import { alarmScopeStorage, useSessionStore } from '@/stores/session'

type ActionState = { allowed: boolean; reason: string }
type Row = Record<string, string | number | boolean | null> & {
  id: number
  status: string
  actions: Record<string, ActionState>
}

const ENDPOINT = '/api/alarm'
const columns = ["报警编号", "报警类型", "报警等级", "所属工区", "触发设备", "触发时间", "确认人员", "处置人员", "处置说明", "报警状态"]
const actions = ["确认报警", "处置报警", "忽略报警"]
const statuses = ["待确认", "已确认", "已处置", "已忽略"]

const session = useSessionStore()
const rows = ref<Row[]>([])
const total = ref(0)
const message = ref('')
const messageOk = ref(false)
const keyword = ref('')
const statusFilter = ref('')
// 视图归属按账号角色/工区计算，切走再回来由 localStorage 保持，服务端归属口径不变。
const scope = ref(alarmScopeStorage.get())

const scopeTabs = [
  { label: '全部报警（含跨工区只读）', value: 'all' },
  { label: '我的报警', value: 'mine' },
]

const statsMap = ref<Record<string, number>>({
  今日报警: 0,
  待确认报警: 0,
  高等级报警: 0,
  我的待确认: 0,
})
const stats = computed(() => [
  { label: '今日报警', value: statsMap.value['今日报警'] ?? 0 },
  { label: '待确认报警', value: statsMap.value['待确认报警'] ?? 0 },
  { label: '高等级报警', value: statsMap.value['高等级报警'] ?? 0 },
  { label: '我的待确认', value: statsMap.value['我的待确认'] ?? 0 },
])

function can(row: Row, action: string): boolean {
  return row.actions?.[action]?.allowed ?? false
}

function reason(row: Row, action: string): string {
  return row.actions?.[action]?.reason ?? ''
}

function levelClass(level: unknown): string {
  if (level === '高') {
    return 'level-high'
  }
  if (level === '中') {
    return 'level-mid'
  }
  return 'level-low'
}

function setMessage(text: string, ok = false) {
  message.value = text
  messageOk.value = ok
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function switchScope(next: string) {
  scope.value = next
  alarmScopeStorage.set(next)
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  setMessage('报警事件登记入口尚未接入审批流')
}

async function runAction(action: string, row: Row) {
  setMessage('')
  // 按钮默认禁用，点不到越权动作；若会话过期/账号被换掉仍由后端兜底拒绝。
  const remark = action === '处置报警' ? window.prompt('请填写处置说明（可留空）') : null
  if (action === '处置报警' && remark === null) {
    return
  }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action }, remark: remark ?? undefined }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      // 越权拒绝：把服务端给的具体原因（工区不符/岗位不符/职责分离）显示出来。
      const detail = payload?.detail ?? payload?.message ?? '监测报警动作未生效，请稍后重试'
      setMessage(typeof detail === 'string' ? detail : '监测报警动作未生效，请稍后重试')
      return
    }
    // 确认之后待确认数量与列表同步：同一轮刷新统计与列表。
    await Promise.all([loadStats(), reload()])
    setMessage(String(payload.message ?? '操作成功'), true)
  } catch (error) {
    setMessage(error instanceof Error ? error.message : '监测报警操作失败')
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats/summary`)
    if (!response.ok) {
      return
    }
    const payload = await response.json()
    statsMap.value = payload.stats ?? statsMap.value
  } catch {
    // 统计读不到时保留上一次数值，不阻断列表操作。
  }
}

async function reload() {
  setMessage('')
  const query = new URLSearchParams()
  if (keyword.value.trim()) {
    query.set('keyword', keyword.value.trim())
  }
  if (statusFilter.value) {
    query.set('status', statusFilter.value)
  }
  if (scope.value === 'mine') {
    query.set('scope', 'mine')
  }
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('报警事件列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    setMessage(error instanceof Error ? error.message : '监测报警列表读取失败')
  }
}

async function refreshAll() {
  // 账号切换后重新拉取：归属与可执行动作随岗位变；返回列表后归属仍由服务端按当前账号计算。
  await Promise.all([loadStats(), reload()])
}

onMounted(refreshAll)

// 头部切换账号后，列表归属、可执行动作与统计都按新岗位重算。
watch(
  () => session.operatorId,
  () => {
    void refreshAll()
  },
)
</script>
