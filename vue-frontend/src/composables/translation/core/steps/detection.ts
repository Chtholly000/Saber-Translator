/**
 * 检测步骤
 * 提取自 SequentialPipeline.ts Line 234-287
 */
import { parallelDetect, type ParallelDetectResponse } from '@/api/parallelTranslate'
import type { BubbleCoords, BubbleState, BubbleTextline } from '@/types/bubble'
import type { ImageData as AppImageData } from '@/types/image'
import type { TranslationSettings } from '@/types/settings'
import {
    createBubbleState,
    isBubbleFieldManual,
    mergeGeneratedBubbleState,
    normalizeBubbleStates,
} from '@/utils/bubbleFactory'

export interface DetectionInput {
    imageIndex: number
    image: AppImageData
    translationMode?: string
    pipelineProfile?: string
    forceDetect?: boolean
    settingsSnapshot: TranslationSettings
}

export interface DetectionOutput {
    bubbleCoords: BubbleCoords[]
    bubbleAngles: number[]
    bubblePolygons: number[][][]
    autoDirections: string[]
    textMask?: string  // 文字检测掩膜
    textlinesPerBubble: BubbleTextline[][]
    originalTexts?: string[]
    bubbleStates: BubbleState[]
}
function createBubbleStatesFromDetection(
    image: AppImageData,
    result: {
        bubbleCoords: BubbleCoords[]
        bubbleAngles: number[]
        autoDirections: string[]
        textlinesPerBubble: BubbleTextline[][]
    },
    settingsSnapshot: TranslationSettings
): BubbleState[] {
    const textStyle = settingsSnapshot.textStyle

    return result.bubbleCoords.map((coords, index) => {
        const autoDirection = result.autoDirections[index] === 'h'
            ? 'horizontal'
            : result.autoDirections[index] === 'v'
                ? 'vertical'
                : (coords[3] - coords[1]) > (coords[2] - coords[0])
                    ? 'vertical'
                    : 'horizontal'

        const textDirection = textStyle.layoutDirection === 'vertical' || textStyle.layoutDirection === 'horizontal'
            ? textStyle.layoutDirection
            : autoDirection

        return createBubbleState({
            coords,
            polygon: [],
            originalText: image.originalTexts?.[index] || '',
            translatedText: image.bubbleTexts?.[index] || '',
            textboxText: image.textboxTexts?.[index] || '',
            rotationAngle: result.bubbleAngles[index] || 0,
            textDirection,
            autoTextDirection: autoDirection,
            textlines: result.textlinesPerBubble[index] || [],
            fontSize: textStyle.fontSize,
            fontFamily: textStyle.fontFamily,
            textColor: textStyle.textColor,
            fillColor: textStyle.fillColor,
            strokeEnabled: textStyle.strokeEnabled,
            strokeColor: textStyle.strokeColor,
            strokeWidth: textStyle.strokeWidth,
            lineSpacing: textStyle.lineSpacing,
            textAlign: textStyle.textAlign,
            inpaintMethod: textStyle.inpaintMethod
        })
    })
}

function intersectionOverUnion(left: BubbleCoords, right: BubbleCoords): number {
    const [leftX1, leftY1, leftX2, leftY2] = left
    const [rightX1, rightY1, rightX2, rightY2] = right
    const intersectionWidth = Math.max(0, Math.min(leftX2, rightX2) - Math.max(leftX1, rightX1))
    const intersectionHeight = Math.max(0, Math.min(leftY2, rightY2) - Math.max(leftY1, rightY1))
    const intersection = intersectionWidth * intersectionHeight
    const leftArea = Math.abs(leftX2 - leftX1) * Math.abs(leftY2 - leftY1)
    const rightArea = Math.abs(rightX2 - rightX1) * Math.abs(rightY2 - rightY1)
    const union = leftArea + rightArea - intersection
    return union > 0 ? intersection / union : 0
}

/**
 * A forced detection can improve automatic regions, but it may not erase a
 * person-created bubble or a person-locked field. Matching remains local and
 * geometry based until the remote stage protocol supplies region IDs itself.
 */
function mergeDetectedBubbleStates(
    existing: BubbleState[],
    detected: BubbleState[],
): BubbleState[] {
    const unmatchedExisting = [...existing]
    const merged = detected.map((detectedBubble) => {
        let bestIndex = -1
        let bestScore = 0
        unmatchedExisting.forEach((existingBubble, index) => {
            const score = intersectionOverUnion(existingBubble.coords, detectedBubble.coords)
            if (score > bestScore) {
                bestScore = score
                bestIndex = index
            }
        })

        if (bestIndex < 0 || bestScore < 0.2) {
            return detectedBubble
        }

        const existingBubble = unmatchedExisting.splice(bestIndex, 1)[0]
        return existingBubble
            ? mergeGeneratedBubbleState(existingBubble, detectedBubble)
            : detectedBubble
    })

    // A detector missing a manually edited bubble is not permission to remove
    // it. The user can still delete it explicitly in the editor.
    return [
        ...merged,
        ...unmatchedExisting.filter((bubble) => (bubble.manualFields || []).some((field) =>
            isBubbleFieldManual(bubble, field)
        )),
    ]
}

export async function executeDetection(input: DetectionInput): Promise<DetectionOutput> {
    const { imageIndex, image, translationMode = 'standard', forceDetect = false, settingsSnapshot } = input
    const pipelineProfile = input.pipelineProfile || 'local_saber'

    // 如果图片已有 bubbleStates 数据（包括空数组），跳过检测
    // - bubbleStates === null/undefined: 从未处理过，需要自动检测
    // - bubbleStates === []: 用户主动清空，跳过检测（避免"框复活"）
    // - bubbleStates.length > 0: 有气泡数据，复用已有数据
    const existingBubbles = image.bubbleStates === null || image.bubbleStates === undefined
        ? image.bubbleStates
        : normalizeBubbleStates(image.bubbleStates)
    if (!forceDetect && existingBubbles !== null && existingBubbles !== undefined) {
        if (existingBubbles.length > 0) {
            console.log(`图片 ${imageIndex + 1} 已有 ${existingBubbles.length} 个气泡，跳过检测`)
            // 坐标需要转换为整数，后端 numpy 切片需要整数索引
            return {
                bubbleCoords: existingBubbles.map(s =>
                    s.coords.map(c => Math.round(c)) as BubbleCoords
                ),
                bubbleAngles: existingBubbles.map(s => s.rotationAngle || 0),
                bubblePolygons: existingBubbles.map(s => s.polygon || []),
                autoDirections: existingBubbles.map(s => s.autoTextDirection || s.textDirection || 'vertical'),
                textMask: image.textMask ?? undefined,  // 从持久化数据中获取掩膜
                textlinesPerBubble: existingBubbles.map((bubble, index) =>
                    bubble.textlines && bubble.textlines.length > 0
                        ? bubble.textlines
                        : image.textlinesPerBubble?.[index] || []
                ),
                originalTexts: existingBubbles.map(s => s.originalText || ''),
                bubbleStates: existingBubbles
            }
        } else {
            console.log(`图片 ${imageIndex + 1} 气泡已被清空，跳过检测`)
            return {
                bubbleCoords: [],
                bubbleAngles: [],
                bubblePolygons: [],
                autoDirections: [],
                textMask: undefined,
                textlinesPerBubble: [],
                originalTexts: [],
                bubbleStates: []
            }
        }
    }

    const settings = settingsSnapshot
    const base64 = extractBase64(image.originalDataURL)

    // 步骤1: 使用用户选择的检测器进行检测（获取文本框）
    const response: ParallelDetectResponse = await parallelDetect({
        image: base64,
        pipeline_profile: pipelineProfile,
        translation_mode: translationMode,
        translation_scope: 'image',
        detector_type: settings.textDetector,
        min_text_block_area_percent: settings.minTextBlockAreaPercent,
        enable_aux_yolo_detection: settings.enableAuxYoloDetection,
        aux_yolo_conf_threshold: settings.auxYoloConfThreshold,
        aux_yolo_overlap_threshold: settings.auxYoloOverlapThreshold,
        enable_saber_yolo_refine: settings.enableSaberYoloRefine,
        saber_yolo_refine_overlap_threshold: settings.saberYoloRefineOverlapThreshold,
        box_expand_ratio: settings.boxExpand.ratio,
        box_expand_top: settings.boxExpand.top,
        box_expand_bottom: settings.boxExpand.bottom,
        box_expand_left: settings.boxExpand.left,
        box_expand_right: settings.boxExpand.right
    })

    if (!response.success) {
        throw new Error(response.error || '检测失败')
    }

    // 步骤2: 固定使用 Default 检测器生成精确文字掩膜
    // 无论用户选择哪个检测器，都统一使用 Default 生成掩膜
    // 这样所有检测器都能享受精确掩膜的好处
    let textMaskData: string | undefined = undefined

    console.log(`使用 Default 检测器生成精确文字掩膜...`)
    try {
        const maskResponse: ParallelDetectResponse = await parallelDetect({
            image: base64,
            pipeline_profile: pipelineProfile,
            translation_mode: translationMode,
            translation_scope: 'image',
            detector_type: 'default',  // 固定使用 Default 检测器生成掩膜
            enable_aux_yolo_detection: false,  // 掩膜路径不需要辅助检测
            enable_saber_yolo_refine: false,  // 掩膜路径不需要二阶段纠错
            box_expand_ratio: 0,       // 掩膜生成不需要扩展
            box_expand_top: 0,
            box_expand_bottom: 0,
            box_expand_left: 0,
            box_expand_right: 0
        })

        if (maskResponse.success && maskResponse.raw_mask) {
            textMaskData = maskResponse.raw_mask
            console.log(`✅ 精确文字掩膜生成成功`)
        } else {
            console.warn(`⚠️ Default 检测器未能生成掩膜`)
        }
    } catch (error) {
        console.error(`❌ 生成精确文字掩膜失败:`, error)
        // 掩膜生成失败不影响主流程，继续使用检测结果
    }

    const detectionResult = {
        bubbleCoords: (response.bubble_coords || []) as BubbleCoords[],
        bubbleAngles: response.bubble_angles || [],
        bubblePolygons: response.bubble_polygons || [],
        autoDirections: response.auto_directions || [],
        textMask: textMaskData,  // 返回生成的精确掩膜
        textlinesPerBubble: response.textlines_per_bubble || []
    }
    const detectedBubbleStates = createBubbleStatesFromDetection(image, detectionResult, settingsSnapshot)
    const bubbleStates = forceDetect && Array.isArray(existingBubbles)
        ? mergeDetectedBubbleStates(existingBubbles, detectedBubbleStates)
        : detectedBubbleStates

    return {
        ...detectionResult,
        bubbleCoords: bubbleStates.map((bubble) => bubble.coords),
        bubbleAngles: bubbleStates.map((bubble) => bubble.rotationAngle || 0),
        bubblePolygons: bubbleStates.map((bubble) => bubble.polygon || []),
        autoDirections: bubbleStates.map((bubble) => bubble.autoTextDirection || bubble.textDirection || 'vertical'),
        textlinesPerBubble: bubbleStates.map((bubble) => bubble.textlines || []),
        originalTexts: bubbleStates.map((bubble) => bubble.originalText || ''),
        bubbleStates,
    }
}

function extractBase64(dataUrl: string): string {
    if (dataUrl.includes('base64,')) {
        return dataUrl.split('base64,')[1] || ''
    }
    return dataUrl
}
