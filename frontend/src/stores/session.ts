import { defineStore } from 'pinia'

export type Role = '值班员' | '调度' | '检修人员'

/** 可切换的演示账号：岗位决定动作权限，工区决定本工区/跨工区口径。 */
export interface Identity {
  role: Role
  zone: string
  operator: string
}

export const IDENTITIES: Identity[] = [
  { role: '值班员', zone: '一工区', operator: '王值班' },
  { role: '值班员', zone: '二工区', operator: '孙值班' },
  { role: '调度', zone: '', operator: '李调度' },
  { role: '检修人员', zone: '一工区', operator: '赵检修' },
]

export const useSessionStore = defineStore('session', {
  state: () => ({
    identity: { role: '值班员', zone: '一工区', operator: '王值班' } as Identity,
    shiftLabel: '白班 08:00-20:00',
    scope: '轨道交通信号设备检修平台',
  }),
  getters: {
    operator: (state) => state.identity.operator,
    role: (state) => state.identity.role,
    zone: (state) => state.identity.zone,
    canOperate: (state) => state.identity.operator.length > 0,
  },
  actions: {
    setIdentity(identity: Identity) {
      this.identity = identity
    },
    setShift(label: string) {
      this.shiftLabel = label
    },
    authHeaders(extra?: Record<string, string>): Record<string, string> {
      return {
        'X-Operator-Role': this.identity.role,
        'X-Operator-Zone': this.identity.zone,
        'X-Operator-Name': this.identity.operator,
        ...extra,
      }
    },
  },
})
