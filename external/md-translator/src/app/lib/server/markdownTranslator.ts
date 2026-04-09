import pLimit from "p-limit";
import pRetry from "p-retry";

import { filterMarkdownLines, PLACEHOLDER_SPLIT_REGEX, PLACEHOLDER_TEST_REGEX } from "@/app/[locale]/markdownUtils";
import { defaultConfigs, DEFAULT_SYS_PROMPT, DEFAULT_USER_PROMPT } from "@/app/lib/translation/config";
import { translationServices } from "@/app/lib/translation/services";
import type { TranslateTextParams, TranslationConfig } from "@/app/lib/translation/types";
import { cleanTranslatedText } from "@/app/lib/translation/utils";
import { splitTextIntoLines } from "@/app/utils";

export interface MarkdownTranslateOptions {
  text: string;
  sourceLanguage?: string;
  targetLanguage?: string;
  translationMethod?: string;
  config?: TranslationConfig;
  markdownOptions?: {
    translateFrontmatter?: boolean;
    translateMultilineCode?: boolean;
    translateLatex?: boolean;
    translateLinkText?: boolean;
  };
  retryCount?: number;
  retryTimeout?: number;
}

type SegmentMappingEntry =
  | { type: "placeholder" | "empty"; value: string }
  | { type: "text"; index: number; leading: string; trailing: string };

const DEFAULT_MARKDOWN_OPTIONS = {
  translateFrontmatter: false,
  translateMultilineCode: false,
  translateLatex: false,
  translateLinkText: true,
};

const buildRetryConfig = (retryCount: number) => ({
  retries: retryCount,
  factor: 2,
  minTimeout: 1000,
  maxTimeout: 30000,
  randomize: true,
});

const buildCustomLlmUrl = (baseUrl: string | undefined): string | undefined => {
  const trimmed = baseUrl?.trim();
  if (!trimmed) {
    return undefined;
  }
  if (trimmed.endsWith("/chat/completions")) {
    return trimmed;
  }
  return `${trimmed.replace(/\/+$/, "")}/chat/completions`;
};

const resolveConfig = (translationMethod: string, inputConfig: TranslationConfig | undefined): TranslationConfig => {
  const baseConfig = { ...(defaultConfigs[translationMethod as keyof typeof defaultConfigs] || {}) };
  const merged = { ...baseConfig, ...(inputConfig || {}) };

  if (!merged.apiKey) {
    merged.apiKey = process.env.DEEPSEEK_API_KEY || "";
  }

  if (!merged.model) {
    merged.model = process.env.DEEPSEEK_MODEL || "deepseek-chat";
  }

  if ((translationMethod === "llm" || translationMethod === "openai") && !merged.url) {
    merged.url = buildCustomLlmUrl(process.env.DEEPSEEK_BASE_URL);
  }

  if (!merged.sysPrompt) {
    merged.sysPrompt = DEFAULT_SYS_PROMPT;
  }

  if (!merged.userPrompt) {
    merged.userPrompt = DEFAULT_USER_PROMPT;
  }

  return merged;
};

const buildTranslateParams = (
  text: string,
  translationMethod: string,
  sourceLanguage: string,
  targetLanguage: string,
  config: TranslationConfig,
  retryTimeoutMs: number,
  fullText?: string,
): { params: TranslateTextParams; cleanup: () => void } => {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), retryTimeoutMs);

  const params: TranslateTextParams = {
    text,
    cacheSuffix: "paperreader-server",
    translationMethod,
    targetLanguage,
    sourceLanguage,
    useCache: false,
    signal: controller.signal,
    ...(config.apiKey !== undefined ? { apiKey: config.apiKey } : {}),
    ...(config.region !== undefined ? { region: config.region } : {}),
    ...(config.url !== undefined ? { url: config.url } : {}),
    ...(config.model !== undefined ? { model: config.model } : {}),
    ...(config.apiVersion !== undefined ? { apiVersion: config.apiVersion } : {}),
    ...(config.temperature !== undefined ? { temperature: config.temperature } : {}),
    ...(config.sysPrompt !== undefined ? { sysPrompt: config.sysPrompt } : {}),
    ...(config.userPrompt !== undefined ? { userPrompt: config.userPrompt } : {}),
    ...(config.useRelay !== undefined ? { useRelay: config.useRelay } : {}),
    ...(config.enableThinking !== undefined ? { enableThinking: config.enableThinking } : {}),
    ...(config.domains !== undefined ? { domains: config.domains } : {}),
    ...(fullText !== undefined ? { fullText } : {}),
  };

  return {
    params,
    cleanup: () => clearTimeout(timeoutId),
  };
};

const translateSingleSegment = async (
  text: string,
  translationMethod: string,
  sourceLanguage: string,
  targetLanguage: string,
  config: TranslationConfig,
  retryCount: number,
  retryTimeoutMs: number,
  fullText?: string,
): Promise<string> => {
  const service = translationServices[translationMethod];
  if (!service) {
    throw new Error(`Unsupported translation method: ${translationMethod}`);
  }

  const retryConfig = buildRetryConfig(retryCount);

  return await pRetry(
    async () => {
      const { params, cleanup } = buildTranslateParams(
        text,
        translationMethod,
        sourceLanguage,
        targetLanguage,
        config,
        retryTimeoutMs,
        fullText,
      );
      try {
        const translated = await service(params);
        return cleanTranslatedText(translated);
      } finally {
        cleanup();
      }
    },
    retryConfig,
  );
};

export const translateMarkdown = async (options: MarkdownTranslateOptions): Promise<string> => {
  const {
    text,
    sourceLanguage = "en",
    targetLanguage = "zh",
    translationMethod = "llm",
    config: inputConfig,
    markdownOptions,
    retryCount = 3,
    retryTimeout = 60,
  } = options;

  if (!text.trim()) {
    throw new Error("Text to translate is empty.");
  }

  const config = resolveConfig(translationMethod, inputConfig);
  const lines = splitTextIntoLines(text);
  const mdOptions = {
    ...DEFAULT_MARKDOWN_OPTIONS,
    ...(markdownOptions || {}),
  };

  const {
    contentLines,
    frontmatterPlaceholders,
    codePlaceholders,
    linkPlaceholders,
    headingPlaceholders,
    listPlaceholders,
    blockquotePlaceholders,
    strongPlaceholders,
    latexBlockPlaceholders,
    latexInlinePlaceholders,
    htmlPlaceholders,
  } = filterMarkdownLines(lines, mdOptions);

  const textsToTranslate: string[] = [];
  const lineSegments: { mapping: SegmentMappingEntry[] }[] = [];

  for (const line of contentLines) {
    const segments = line.split(PLACEHOLDER_SPLIT_REGEX);
    const mapping: SegmentMappingEntry[] = [];

    for (const segment of segments) {
      if (PLACEHOLDER_TEST_REGEX.test(segment)) {
        mapping.push({ type: "placeholder", value: segment });
        continue;
      }

      const leadingSpace = segment.match(/^\s*/)?.[0] || "";
      const trailingSpace = segment.match(/\s*$/)?.[0] || "";
      const trimmedSegment = segment.trim();

      if (!trimmedSegment) {
        mapping.push({ type: "empty", value: segment });
      } else {
        mapping.push({
          type: "text",
          index: textsToTranslate.length,
          leading: leadingSpace,
          trailing: trailingSpace,
        });
        textsToTranslate.push(trimmedSegment);
      }
    }

    lineSegments.push({ mapping });
  }

  const concurrency = Math.max(Number(config.batchSize) || 10, 1);
  const retryTimeoutMs = Math.max(1, retryTimeout) * 1000;
  const fullText = config.userPrompt?.includes("${fullText}") ? textsToTranslate.join("\n") : undefined;
  const limit = pLimit(concurrency);
  const translatedTexts = new Array<string>(textsToTranslate.length);

  await Promise.all(
    textsToTranslate.map((segment, index) =>
      limit(async () => {
        translatedTexts[index] = await translateSingleSegment(
          segment,
          translationMethod,
          sourceLanguage,
          targetLanguage,
          config,
          retryCount,
          retryTimeoutMs,
          fullText,
        );
      }),
    ),
  );

  const translatedLines = lineSegments.map(({ mapping }) =>
    mapping
      .map((entry) => {
        if (entry.type === "text") {
          return `${entry.leading}${translatedTexts[entry.index || 0]}${entry.trailing}`;
        }
        return entry.value || "";
      })
      .join(""),
  );

  let translatedMarkdown = translatedLines.join("\n");
  const allPlaceholders = new Map([
    ...Object.entries(frontmatterPlaceholders),
    ...Object.entries(codePlaceholders),
    ...Object.entries(latexBlockPlaceholders),
    ...Object.entries(linkPlaceholders),
    ...Object.entries(headingPlaceholders),
    ...Object.entries(listPlaceholders),
    ...Object.entries(blockquotePlaceholders),
    ...Object.entries(latexInlinePlaceholders),
    ...Object.entries(strongPlaceholders),
    ...Object.entries(htmlPlaceholders),
  ]);

  const sortedPlaceholders = Array.from(allPlaceholders.entries()).sort((a, b) => b[0].length - a[0].length);
  for (const [placeholder, content] of sortedPlaceholders) {
    const replacement = placeholder.includes("LATEX_") ? content.replace(/\$/g, "$$$$") : content;
    translatedMarkdown = translatedMarkdown.replaceAll(placeholder, replacement);
  }

  return translatedMarkdown;
};
