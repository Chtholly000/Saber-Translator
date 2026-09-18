import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useBubbleStore } from '@/stores/bubbleStore'
import { createBubbleState } from '@/utils/bubbleFactory'

describe('bubbleStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('recomputes autoTextDirection when bubble coords change', () => {
    const bubbleStore = useBubbleStore()

    bubbleStore.setBubbles([
      createBubbleState({
        coords: [0, 0, 200, 100],
        polygon: [],
        textDirection: 'auto',
        autoTextDirection: 'horizontal',
      }),
    ])

    bubbleStore.updateBubble(0, {
      coords: [0, 0, 100, 220],
    })

    expect(bubbleStore.bubbles[0]?.autoTextDirection).toBe('vertical')
  })

  it('records direct editor changes as manual locks without changing the bubble ID', () => {
    const bubbleStore = useBubbleStore()
    const bubble = createBubbleState({
      originalText: 'OCR 原文',
      translatedText: '模型译文',
    })

    bubbleStore.setBubbles([bubble])
    bubbleStore.updateBubble(0, {
      originalText: '人工校对原文',
      translatedText: '人工校对译文',
      fontSize: 26,
    })

    expect(bubbleStore.bubbles[0]?.bubbleId).toBe(bubble.bubbleId)
    expect(bubbleStore.bubbles[0]?.manualFields).toEqual(expect.arrayContaining([
      'originalText',
      'translatedText',
      'style',
    ]))
  })
})
