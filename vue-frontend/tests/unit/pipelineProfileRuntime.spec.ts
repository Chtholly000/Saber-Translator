import { describe, expect, it } from 'vitest'
import { createPipelineRuntime } from '@/composables/translation/core/runtime'
import { createDefaultSettings } from '@/stores/settings/defaults'

describe('pipeline profile runtime snapshot', () => {
  it('normalizes and freezes the configured profile for one automatic run', () => {
    const settings = createDefaultSettings()
    settings.automaticPipelineProfile = 'Modal-MTU'

    const runtime = createPipelineRuntime('standard', {
      settingsSnapshot: settings,
      sessionPath: null,
      bookId: null,
      chapterId: null,
    })

    expect(runtime.pipelineProfile).toBe('modal_mtu')
    settings.automaticPipelineProfile = 'local_saber'
    expect(runtime.pipelineProfile).toBe('modal_mtu')
  })
})
