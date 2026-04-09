import { NextRequest, NextResponse } from "next/server";

import { translateMarkdown } from "@/app/lib/server/markdownTranslator";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const translatedText = await translateMarkdown({
      text: body?.text || "",
      sourceLanguage: body?.sourceLanguage || "en",
      targetLanguage: body?.targetLanguage || "zh",
      translationMethod: body?.translationMethod || "llm",
      config: body?.config || {},
      markdownOptions: body?.markdownOptions || {},
      retryCount: body?.retryCount ?? 3,
      retryTimeout: body?.retryTimeout ?? 60,
    });

    return NextResponse.json({
      success: true,
      translatedText,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown translation error";
    return NextResponse.json(
      {
        success: false,
        error: message,
      },
      { status: 500 },
    );
  }
}
