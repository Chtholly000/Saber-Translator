import { beforeEach, describe, expect, it, vi } from 'vitest'

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }))
vi.mock('@/api/client', () => ({ apiClient: { get: getMock } }))
import { usesLocalStage } from '@/api/parallelTranslate'

describe('per-stage configuration ownership', () => {
  beforeEach(() => getMock.mockReset())

  it('looks at the selected stage instead of the profile name', async () => {
    getMock.mockResolvedValue({ success: true, profiles: [
      { name: 'custom_ocr', stage_backends: { ocr: 'my_ocr', translate: 'local' } },
    ] })
    expect(await usesLocalStage('custom_ocr', 'ocr')).toBe(false)
    expect(await usesLocalStage('custom_ocr', 'translate')).toBe(true)
  })

  it('fails when a selected profile is missing instead of sending local credentials', async () => {
    getMock.mockResolvedValue({ success: true, profiles: [] })
    await expect(usesLocalStage('removed', 'ocr')).rejects.toThrow('计算方案不可用')
  })

  it('keeps the built-in local path independent of profile discovery', async () => {
    expect(await usesLocalStage('local_saber', 'ocr')).toBe(true)
    expect(getMock).not.toHaveBeenCalled()
  })
})
