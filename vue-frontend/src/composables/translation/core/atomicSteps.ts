import {
  executeAiTranslate,
  executeColor,
  executeDetection,
  executeInpaint,
  executeOcr,
  executeRender,
  executeAutoGlossary,
  executeTranslate,
} from './steps'
import { persistPage } from './persistenceService'
import type { PipelineRuntime, TaskContext } from './runtime'
import type { BubbleState } from '@/types/bubble'
import { mergeGeneratedBubbleState } from '@/utils/bubbleFactory'

function mergeOcrIntoBubbleStates(
  bubbleStates: BubbleState[] | null | undefined,
  originalTexts: string[],
  ocrResults: TaskContext['ocrResults'],
): BubbleState[] | null | undefined {
  if (!Array.isArray(bubbleStates)) {
    return bubbleStates
  }

  return bubbleStates.map((bubbleState, index) => mergeGeneratedBubbleState(bubbleState, {
    ...bubbleState,
    originalText: originalTexts[index] ?? bubbleState.originalText,
    ocrResult: ocrResults[index] ?? bubbleState.ocrResult ?? null,
  }))
}

function mergeTranslationIntoBubbleStates(
  bubbleStates: BubbleState[] | null | undefined,
  translatedTexts: string[],
  textboxTexts: string[],
): {
  bubbleStates: BubbleState[] | null | undefined
  translatedTexts: string[]
  textboxTexts: string[]
} {
  if (!Array.isArray(bubbleStates)) {
    return { bubbleStates, translatedTexts, textboxTexts }
  }

  const mergedBubbleStates = bubbleStates.map((bubbleState, index) => mergeGeneratedBubbleState(bubbleState, {
    ...bubbleState,
    translatedText: translatedTexts[index] ?? bubbleState.translatedText,
    textboxText: textboxTexts[index] ?? bubbleState.textboxText,
  }))

  return {
    bubbleStates: mergedBubbleStates,
    translatedTexts: mergedBubbleStates.map((bubble) => bubble.translatedText),
    textboxTexts: mergedBubbleStates.map((bubble) => bubble.textboxText),
  }
}

export type AtomicStepName =
  | 'detection'
  | 'ocr'
  | 'color'
  | 'autoGlossary'
  | 'translate'
  | 'inpaint'
  | 'render'
  | 'save'

export type BatchAtomicStepName = 'aiTranslate'

export async function executeAtomicStep(
  step: AtomicStepName,
  context: TaskContext,
  runtime: PipelineRuntime
): Promise<TaskContext> {
  switch (step) {
    case 'detection': {
      const result = await executeDetection({
        imageIndex: context.imageIndex,
        image: context.sourceImage,
        translationMode: runtime.mode,
        pipelineProfile: runtime.pipelineProfile,
        forceDetect: false,
        settingsSnapshot: runtime.settingsSnapshot,
      })
      return {
        ...context,
        status: 'processing',
        bubbleCoords: result.bubbleCoords,
        bubbleAngles: result.bubbleAngles,
        bubblePolygons: result.bubblePolygons,
        autoDirections: result.autoDirections,
        textMask: result.textMask,
        textlinesPerBubble: result.textlinesPerBubble,
        originalTexts: result.originalTexts || [],
        bubbleStates: result.bubbleStates,
      }
    }
    case 'ocr': {
      const result = await executeOcr({
        imageIndex: context.imageIndex,
        image: context.sourceImage,
        translationMode: runtime.mode,
        pipelineProfile: runtime.pipelineProfile,
        bubbleCoords: context.bubbleCoords,
        bubbleStates: context.bubbleStates,
        textlinesPerBubble: context.textlinesPerBubble,
        settingsSnapshot: runtime.settingsSnapshot,
      })
      const bubbleStates = mergeOcrIntoBubbleStates(
        context.bubbleStates,
        result.originalTexts,
        result.ocrResults,
      )
      return {
        ...context,
        status: 'processing',
        originalTexts: Array.isArray(bubbleStates)
          ? bubbleStates.map((bubble) => bubble.originalText)
          : result.originalTexts,
        ocrResults: result.ocrResults,
        bubbleStates,
      }
    }
    case 'color': {
      const result = await executeColor({
        imageIndex: context.imageIndex,
        image: context.sourceImage,
        translationMode: runtime.mode,
        bubbleCoords: context.bubbleCoords,
        bubbleStates: context.bubbleStates,
        textlinesPerBubble: context.textlinesPerBubble,
      })
      return {
        ...context,
        status: 'processing',
        colors: result.colors,
      }
    }
    case 'autoGlossary': {
      const result = await executeAutoGlossary({
        originalTexts: context.originalTexts,
        settingsSnapshot: runtime.settingsSnapshot,
        bookTranslationConstraints: runtime.bookTranslationConstraints,
        isBookshelfMode: runtime.isBookshelfMode,
      })
      runtime.bookTranslationConstraints = JSON.parse(JSON.stringify(result.bookTranslationConstraints))
      return {
        ...context,
        status: 'processing',
        autoGlossaryStats: {
          added: context.autoGlossaryStats.added + result.autoGlossaryStats.added,
          duplicates: context.autoGlossaryStats.duplicates + result.autoGlossaryStats.duplicates,
          failedPages: context.autoGlossaryStats.failedPages + result.autoGlossaryStats.failedPages,
        },
      }
    }
    case 'translate': {
      const result = await executeTranslate({
        imageIndex: context.imageIndex,
        translationMode: runtime.mode,
        pipelineProfile: runtime.pipelineProfile,
        originalTexts: context.originalTexts,
        settingsSnapshot: runtime.settingsSnapshot,
        bookTranslationConstraints: runtime.bookTranslationConstraints,
        isBookshelfMode: runtime.isBookshelfMode,
      })
      const merged = mergeTranslationIntoBubbleStates(
        context.bubbleStates,
        result.translatedTexts,
        result.textboxTexts,
      )
      return {
        ...context,
        status: 'processing',
        translatedTexts: merged.translatedTexts,
        textboxTexts: merged.textboxTexts,
        warnings: result.warnings,
        bubbleStates: merged.bubbleStates,
      }
    }
    case 'inpaint': {
      const result = await executeInpaint({
        imageIndex: context.imageIndex,
        image: context.sourceImage,
        translationMode: runtime.mode,
        pipelineProfile: runtime.pipelineProfile,
        bubbleCoords: context.bubbleCoords,
        bubblePolygons: context.bubblePolygons,
        textMask: context.textMask,
        userMask: context.sourceImage.userMask || undefined,
        settingsSnapshot: runtime.settingsSnapshot,
      })
      return {
        ...context,
        status: 'processing',
        cleanImage: result.cleanImage,
      }
    }
    case 'render': {
      if (!context.cleanImage && runtime.mode === 'removeText' && context.bubbleCoords.length === 0) {
        return {
          ...context,
          status: 'processing',
          finalImage: context.sourceImage.originalDataURL,
          bubbleStates: [],
        }
      }
      if (runtime.mode === 'removeText' && context.translatedTexts.length === 0 && context.textboxTexts.length === 0) {
        return {
          ...context,
          status: 'processing',
          finalImage: context.cleanImage || context.sourceImage.cleanImageData || context.sourceImage.originalDataURL,
          bubbleStates: Array.isArray(context.bubbleStates) ? context.bubbleStates : [],
        }
      }
      const result = await executeRender({
        imageIndex: context.imageIndex,
        cleanImage: context.cleanImage || '',
        bubbleCoords: context.bubbleCoords,
        bubbleAngles: context.bubbleAngles,
        autoDirections: context.autoDirections,
        textlinesPerBubble: context.bubbleStates?.map((bubble) => bubble.textlines || []) || context.textlinesPerBubble,
        existingBubbleStates: context.bubbleStates,
        originalTexts: context.originalTexts,
        ocrResults: context.ocrResults,
        translatedTexts: context.translatedTexts,
        textboxTexts: context.textboxTexts,
        colors: context.colors,
        savedTextStyles: runtime.savedTextStyles,
        currentMode: runtime.mode,
        pipelineProfile: runtime.pipelineProfile,
        settingsSnapshot: runtime.settingsSnapshot,
        renderStylePolicy: {
          fontSize: runtime.savedTextStyles?.autoFontSize ? 'initialize_auto' : 'preserve',
          color: runtime.savedTextStyles?.useAutoTextColor ? 'initialize_auto' : 'preserve',
        },
      })
      return {
        ...context,
        status: 'processing',
        finalImage: result.finalImage,
        bubbleStates: result.bubbleStates,
      }
    }
    case 'save':
      return await persistPage(context, runtime)
  }
}

export async function executeBatchAtomicStep(
  step: BatchAtomicStepName,
  contexts: TaskContext[],
  runtime: PipelineRuntime
): Promise<TaskContext[]> {
  switch (step) {
    case 'aiTranslate': {
      const result = await executeAiTranslate({
        mode: runtime.mode === 'proofread' ? 'proofread' : 'hq',
        tasks: contexts.map((context) => ({
          imageIndex: context.imageIndex,
          image: context.sourceImage,
          originalTexts: context.originalTexts,
          autoDirections: context.autoDirections,
        })),
        settingsSnapshot: runtime.settingsSnapshot,
        bookTranslationConstraints: runtime.bookTranslationConstraints,
        isBookshelfMode: runtime.isBookshelfMode,
      })

      return contexts.map((context) => {
        const taskResult = result.results.find((item) => item.imageIndex === context.imageIndex)
        const merged = mergeTranslationIntoBubbleStates(
          context.bubbleStates,
          taskResult?.translatedTexts || [],
          taskResult?.textboxTexts || [],
        )
        return {
          ...context,
          status: 'processing',
          translatedTexts: merged.translatedTexts,
          textboxTexts: merged.textboxTexts,
          warnings: taskResult?.warnings || [],
          bubbleStates: merged.bubbleStates,
        }
      })
    }
  }
}
