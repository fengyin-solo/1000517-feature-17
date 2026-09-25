<template>
  <section class="page" data-module="alarm">
    <header class="page-head">
      <div>
        <h2>监测报警管理</h2>
        <p class="page-desc">
          按岗位分流：值班员确认本工区触发设备的一般报警，高等级报警由调度确认，检修人员只读；
          同一账号不能在一条报警上既确认又处置或忽略。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="exportRows">导出监测报警清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>报警编号</span>
        <input v-model="filters.keyword" placeholder="按报警编号检索" />
      </label>
      <label class="filter-item">
        <span>报警状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <label class="filter-check">
        <input v-model="filters.mine" type="checkbox" />
        只看我的报警（{{ roleLabel }}口径）
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>报警归属</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td>
            <span class="tag" :class="ownershipClass(row)">{{ row['归属'] }}</span>
          </td>
          <td class="row-actions">
            <button
              v-for="item in allowedActions(row)"
              :key="item.action"
              class="link"
              :class="{ denied: !item.allowed }"
              type="button"
              :title="item.allowed ? item.action : item.reason"
              @click="onActionClick(item, row)"
            >
              {{ item.action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">当前条件下没有可查看的监测报警</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条监测报警记录 · 当前岗位：{{ roleLabel }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

interface AllowedAction {
  action: string
  allowed: boolean
  reason: string
}

type Row = Record<string, string | number | boolean | null> & {
  allowedActions?: AllowedAction[]
}

const ENDPOINT = '/api/alarm'
const columns = ["报警编号", "报警类型", "报警等级", "触发设备", "所属工区", "触发时间", "确认人员", "处置说明", "报警状态"]
const statuses = ["待确认", "已确认", "已处置", "已忽略"]

const session = useSessionStore()
const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = reactive({ keyword: '', status: '', mine: false })
const stats = ref([
  { label: '今日报警', value: 0 },
  { label: '待确认报警', value: 0 },
  { label: '高等级待确认', value: 0 },
  { label: '我的待确认', value: 0 },
])

const roleLabel = computed(() =>
  session.identity.role === '调度'
    ? '调度'
    : `${session.identity.role}·${session.identity.zone}`,
)

function allowedActions(row: Row): AllowedAction[] {
  return (row.allowedActions as AllowedAction[] | undefined) ?? [
    { action: '确认报警', allowed: false, reason: '权限口径未返回' },
    { action: '处置报警', allowed: false, reason: '权限口径未返回' },
    { action: '忽略报警', allowed: false, reason: '权限口径未返回' },
  ]
}

function ownershipClass(row: Row): string {
  const tag = String(row['归属'] ?? '')
  if (tag === '我的报警') return 'tag-mine'
  if (tag === '只读') return 'tag-readonly'
  return 'tag-other'
}

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  filters.mine = false
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

// 越权按钮保持可见但置灰：点击后把后端给出的拒绝原因显示在页脚，
// 说明“为什么不能点”，而不是静默拦截。
function onActionClick(item: AllowedAction, row: Row) {
  if (!item.allowed) {
    errorMessage.value = `${row['报警编号']}：${item.reason}`
    return
  }
  void runAction(item.action, row)
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      headers: session.authHeaders(),
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload) {
      throw new Error(payload?.detail ?? '监测报警动作未生效，请稍后重试')
    }
    if (!payload.ok) {
      // 后端按岗位规则拒绝时必须把原因透传给值班人员。
      errorMessage.value = payload.message
      return
    }
    // 确认之后待确认数量与列表同步刷新。
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '监测报警操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.keyword) query.set('keyword', filters.keyword)
  if (filters.status) query.set('status', filters.status)
  if (filters.mine) query.set('mine', 'true')
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`, {
      headers: session.authHeaders(),
    })
    if (!response.ok) {
      throw new Error('报警事件列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '监测报警列表读取失败'
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`, { headers: session.authHeaders() })
    if (!response.ok) {
      return
    }
    const payload = await response.json()
    stats.value = [
      { label: '今日报警', value: payload.today ?? 0 },
      { label: '待确认报警', value: payload.pending ?? 0 },
      { label: '高等级待确认', value: payload.highPending ?? 0 },
      { label: '我的待确认', value: payload.minePending ?? 0 },
    ]
  } catch {
    // 统计卡片拉取失败不阻断列表，保留上一次的数量。
  }
}

// 顶栏切换岗位/工区后，列表归属与待确认数量按新身份重新计算。
watch(
  () => session.identity,
  () => {
    void Promise.all([reload(), loadStats()])
  },
  { deep: true },
)

onMounted(() => {
  void Promise.all([reload(), loadStats()])
})
</script>
