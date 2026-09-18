import { describe, expect, it } from 'vitest'
import {
  createBubbleState,
  mergeGeneratedBubbleState,
  normalizeBubbleStates,
  updateBubbleState,
} from '@/utils/bubbleFactory'

describe('bubble state contract', () => {
  it('migrates legacy bubbles once while keeping a stable generated ID', () => {
    const [normalized] = normalizeBubbleStates([
      createBubbleState({ bubbleId: '', manualFields: ['geometry', 'invalid' as any] }),
    ])

    expect(normalized?.bubbleId).toMatch(/^bubble_/)
    expect(normalized?.manualFields).toEqual(['geometry'])
    expect(normalizeBubbleStates([normalized!])[0]?.bubbleId).toBe(normalized?.bubbleId)
  })

  it('marks direct editor updates and preserves locked values from generated writes', () => {
    const edited = updateBubbleState(createBubbleState({
      coords: [0, 0, 100, 100],
      translatedText: '人工译文',
      textColor: '#123456',
    }), {
      translatedText: '人工校对后的译文',
      textColor: '#654321',
    })
    const generated = createBubbleState({
      bubbleId: 'worker-should-not-replace-id',
      coords: [5, 5, 90, 90],
      translatedText: '模型译文',
      textColor: '#ffffff',
    })

    const merged = mergeGeneratedBubbleState(edited, generated)

    expect(merged.bubbleId).toBe(edited.bubbleId)
    expect(merged.manualFields).toEqual(expect.arrayContaining(['translatedText', 'style']))
    expect(merged.translatedText).toBe('人工校对后的译文')
    expect(merged.textColor).toBe('#654321')
    expect(merged.coords).toEqual([5, 5, 90, 90])
  })
})
