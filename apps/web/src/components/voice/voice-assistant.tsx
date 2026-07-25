"use client";

import { useState, useRef, useEffect } from "react";
import {
  Mic,
  MicOff,
  Loader2,
  Volume2,
  AlertCircle,
  Sparkles,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { apiClient } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface VoiceQueryResult {
  transcribed_text: string;
  detected_language: string;
  intent: string;
  intent_confidence: number;
  entities: Record<string, unknown>;
  response_text: string;
  audio_response_url: string | null;
  total_time_ms: number;
}

const EXAMPLES = [
  "What's the weather at my field?",
  "Identify this crop disease",
  "Am I eligible for PM-Kisan?",
  "Show my insurance policies",
  "What's the NDVI of my plot?",
];

export function VoiceAssistant() {
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [result, setResult] = useState<VoiceQueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const { user } = useAuthStore();

  async function startRecording() {
    setError(null);
    setResult(null);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, {
          type: mediaRecorder.mimeType || "audio/webm",
        });
        stream.getTracks().forEach((track) => track.stop());
        await processVoiceQuery(audioBlob);
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      setError("Please allow microphone access to use the voice assistant.");
    }
  }

  function stopRecording() {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  }

  async function processVoiceQuery(audioBlob: Blob) {
    setIsProcessing(true);
    setError(null);

    try {
      const formData = new FormData();
      const ext = audioBlob.type.includes("webm")
        ? "webm"
        : audioBlob.type.includes("mp4")
          ? "mp4"
          : "wav";
      formData.append("file", audioBlob, `audio.${ext}`);

      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL}/voice/query`,
        {
          method: "POST",
          body: formData,
          credentials: "include",
          headers: {
            Authorization: `Bearer ${localStorage.getItem("krishisetu.access_token")}`,
          },
        },
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData?.error?.message || "Voice query failed");
      }

      const data: VoiceQueryResult = await response.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Voice processing failed");
    } finally {
      setIsProcessing(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-primary" />
          Voice Assistant
        </CardTitle>
        <CardDescription>
          Ask questions in your language — speak naturally
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Mic button */}
        <div className="flex flex-col items-center gap-3">
          <button
            onClick={isRecording ? stopRecording : startRecording}
            disabled={isProcessing}
            className={`flex h-20 w-20 items-center justify-center rounded-full transition-all ${
              isRecording
                ? "bg-red-500 text-white animate-pulse"
                : "bg-primary text-white hover:bg-primary-700 hover:shadow-lg"
            } ${isProcessing ? "opacity-50 cursor-not-allowed" : ""}`}
          >
            {isProcessing ? (
              <Loader2 className="h-8 w-8 animate-spin" />
            ) : isRecording ? (
              <MicOff className="h-8 w-8" />
            ) : (
              <Mic className="h-8 w-8" />
            )}
          </button>
          <p className="text-sm font-medium text-slate-700">
            {isRecording
              ? "Listening... Tap to stop"
              : isProcessing
                ? "Processing..."
                : "Tap to speak"}
          </p>
        </div>

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 rounded-md bg-red-50 p-3 text-sm text-red-700">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            {error}
          </div>
        )}

        {/* Result */}
        {result && (
          <div className="space-y-3">
            {/* Transcribed text */}
            <div className="rounded-md bg-slate-50 p-3">
              <p className="text-xs font-medium text-slate-500">You said:</p>
              <p className="mt-1 text-sm text-slate-900">{result.transcribed_text}</p>
              <div className="mt-2 flex items-center gap-2 text-xs text-slate-400">
                <span>Language: {result.detected_language}</span>
                <span>·</span>
                <span>Intent: {result.intent}</span>
                <span>·</span>
                <span>{(result.intent_confidence * 100).toFixed(0)}% confidence</span>
              </div>
            </div>

            {/* Response */}
            <div className="rounded-md bg-primary-5 p-3">
              <div className="flex items-start gap-2">
                <Volume2 className="h-4 w-4 text-primary mt-0.5" />
                <div className="flex-1">
                  <p className="text-xs font-medium text-primary">Response:</p>
                  <p className="mt-1 text-sm text-slate-900">{result.response_text}</p>
                </div>
              </div>
            </div>

            {/* Processing time */}
            <p className="text-xs text-slate-400 text-center">
              Processed in {result.total_time_ms}ms
            </p>
          </div>
        )}

        {/* Examples */}
        {!result && !isRecording && !isProcessing && (
          <div>
            <p className="text-xs font-medium text-slate-500 mb-2">Try saying:</p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((example) => (
                <span
                  key={example}
                  className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600"
                >
                  {example}
                </span>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
