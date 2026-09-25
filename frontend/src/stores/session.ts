import { defineStore } from 'pinia'

import { request } from '@/api/client'

export type OperatorInfo = {
  id: string
  name: string
  role: string
  worksite: string | null
  readOnly: boolean
}

// 请求头与本地持久化共用这一个键，client 里不依赖 pinia 实例直接读取。
export const SESSION_STORAGE_KEY = 'signal-maint.operator-id'
const SCOPE_STORAGE_KEY = 'signal-maint.alarm.scope'

const GUEST: OperatorInfo = {
  id: '',
  name: '未识别身份',
  role: '访客',
  worksite: null,
  readOnly: true,
}

export const useSessionStore = defineStore('session', {
  state: () => ({
    operatorId: localStorage.getItem(SESSION_STORAGE_KEY) ?? 'U1001',
    operators: [] as OperatorInfo[],
    shiftLabel: '白班 08:00-20:00',
    scope: '轨道交通信号设备检修平台',
  }),
  getters: {
    operator(state): OperatorInfo {
      return state.operators.find((item) => item.id === state.operatorId) ?? GUEST
    },
    canOperate(): boolean {
      return this.operator.id.length > 0 && !this.operator.readOnly
    },
  },
  actions: {
    async loadOperators() {
      try {
        const response = await request('/api/operators')
        if (!response.ok) {
          return
        }
        const payload = (await response.json()) as { operators: OperatorInfo[] }
        this.operators = payload.operators ?? []
        // 本地存的账号已经下线时回退到第一个值班，避免悄悄变成只读访客。
        if (this.operatorId && !this.operators.some((item) => item.id === this.operatorId)) {
          const firstDuty = this.operators.find((item) => item.role === '值班')
          this.setOperator(firstDuty?.id ?? this.operators[0]?.id ?? '')
        }
      } catch {
        // 目录拉不到时按访客处理，页面仍可只读浏览。
      }
    },
    setOperator(id: string) {
      this.operatorId = id
      if (id) {
        localStorage.setItem(SESSION_STORAGE_KEY, id)
      } else {
        localStorage.removeItem(SESSION_STORAGE_KEY)
      }
    },
    setShift(label: string) {
      this.shiftLabel = label
    },
  },
})

export const alarmScopeStorage = {
  get(): string {
    return localStorage.getItem(SCOPE_STORAGE_KEY) ?? 'all'
  },
  set(scope: string) {
    localStorage.setItem(SCOPE_STORAGE_KEY, scope)
  },
}
