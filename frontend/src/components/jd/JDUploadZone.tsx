// frontend/src/components/jd/JDUploadZone.tsx
// 职位截图/文件上传区（US-4）
// - 支持多文件选择（截图/PDF/TXT）
// - 文件列表可逐个删除
// - 点击"开始分析"触发 OCR + LLM 结构化提取
// - 支持拖拽上传
// - 分步进度显示：上传中 → OCR 解析中 → AI 结构化提取中
// - 分析成功回调 onAnalyzed(result)

import { useEffect, useRef, useState } from 'react';
import { analyzeJD } from '@/lib/api';
import type { JDAnalysisResult } from '@/types/jd';

interface JDUploadZoneProps {
  /** 分析成功后回调，父组件据此切换为 JDCard */
  onAnalyzed: (result: JDAnalysisResult) => void;
}

/** 上传状态机 */
type JDStatus = 'idle' | 'analyzing' | 'error';

/** 分析阶段 */
type AnalysisStage = 'uploading' | 'ocr' | 'llm';

const ACCEPT = '.png,.jpg,.jpeg,.webp,.pdf,.txt,.doc,.docx';
const VALID_EXTS = ['.png', '.jpg', '.jpeg', '.webp', '.pdf', '.txt', '.doc', '.docx'];

/** 阶段配置：label + 预计耗时（秒）+ 进度区间 */
const STAGES: { stage: AnalysisStage; label: string; minProgress: number; maxProgress: number; estSeconds: number }[] = [
  { stage: 'uploading', label: '上传文件中', minProgress: 0, maxProgress: 10, estSeconds: 2 },
  { stage: 'ocr', label: 'OCR 解析中', minProgress: 10, maxProgress: 75, estSeconds: 60 },
  { stage: 'llm', label: 'AI 结构化提取中', minProgress: 75, maxProgress: 100, estSeconds: 10 },
];

function isValidFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return VALID_EXTS.some((ext) => name.endsWith(ext));
}

function getFileIcon(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  if (['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp'].includes(ext)) return '🖼';
  if (ext === 'pdf') return '📄';
  if (ext === 'txt') return '📝';
  if (['doc', 'docx'].includes(ext)) return '📄';
  return '📄';
}

export default function JDUploadZone({ onAnalyzed }: JDUploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<JDStatus>('idle');
  const [isDragging, setIsDragging] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [fileList, setFileList] = useState<File[]>([]);

  // 分步进度状态
  const [stage, setStage] = useState<AnalysisStage>('uploading');
  const [progress, setProgress] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const busy = status === 'analyzing';

  /** 启动进度计时器 */
  function startProgressTimer() {
    const startTime = Date.now();
    setStage('uploading');
    setProgress(0);
    setElapsed(0);

    timerRef.current = setInterval(() => {
      const sec = (Date.now() - startTime) / 1000;
      setElapsed(sec);

      // 根据已过时间计算当前阶段和进度
      let currentStage: AnalysisStage = 'uploading';
      let currentProgress = 0;
      let stageStart = 0;

      for (const s of STAGES) {
        if (sec >= stageStart && sec < stageStart + s.estSeconds) {
          currentStage = s.stage;
          const stageProgress = (sec - stageStart) / s.estSeconds;
          currentProgress = s.minProgress + (s.maxProgress - s.minProgress) * Math.min(stageProgress, 1);
          break;
        }
        stageStart += s.estSeconds;
        currentProgress = s.maxProgress;
        currentStage = s.stage;
      }

      // 超过总预计时间后，停留在 95%
      const totalEst = STAGES.reduce((sum, s) => sum + s.estSeconds, 0);
      if (sec >= totalEst) {
        setStage('llm');
        setProgress(95);
        return;
      }

      setStage(currentStage);
      setProgress(currentProgress);
    }, 200);
  }

  /** 停止进度计时器 */
  function stopProgressTimer() {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }

  // 组件卸载时清理计时器
  useEffect(() => {
    return () => stopProgressTimer();
  }, []);

  /** 添加文件到列表（过滤无效格式 + 去重） */
  function addFiles(newFiles: File[]) {
    const valid = newFiles.filter(isValidFile);
    if (valid.length < newFiles.length) {
      setStatus('error');
      setErrorMsg('部分文件格式不支持，已过滤。仅支持 PNG/JPG/PDF/TXT 等');
    } else {
      setStatus('idle');
      setErrorMsg(null);
    }
    // 去重（按文件名 + 大小）
    setFileList((prev) => {
      const existing = new Set(prev.map((f) => `${f.name}-${f.size}`));
      const filtered = valid.filter((f) => !existing.has(`${f.name}-${f.size}`));
      return [...prev, ...filtered];
    });
  }

  /** 删除指定索引的文件 */
  function removeFile(index: number) {
    setFileList((prev) => prev.filter((_, i) => i !== index));
  }

  /** 开始分析 */
  async function handleAnalyze() {
    if (fileList.length === 0 || busy) return;

    setStatus('analyzing');
    setErrorMsg(null);
    startProgressTimer();

    try {
      const result = await analyzeJD(fileList);
      stopProgressTimer();
      setProgress(100);
      setStatus('idle');
      setFileList([]); // 清空列表
      onAnalyzed(result);
    } catch (err) {
      stopProgressTimer();
      setStatus('error');
      setErrorMsg(err instanceof Error ? err.message : '分析失败，请重试');
    }
  }

  function openPicker() {
    if (busy) return;
    inputRef.current?.click();
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) addFiles(files);
    e.target.value = '';
  }

  function handleDragOver(e: React.DragEvent) {
    if (busy) return;
    e.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(false);
  }

  function handleDrop(e: React.DragEvent) {
    if (busy) return;
    e.preventDefault();
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files || []);
    if (files.length > 0) addFiles(files);
  }

  const borderCls = isDragging
    ? 'border-brand-primary bg-brand-primary-muted'
    : status === 'error'
      ? 'border-error'
      : 'border-border-default';

  // 获取当前阶段信息
  const currentStageInfo = STAGES.find((s) => s.stage === stage);
  const stageLabel = currentStageInfo?.label ?? '处理中';
  const fileCount = fileList.length;

  return (
    <div className="space-y-2">
      {/* 上传区域 */}
      <div
        onClick={openPicker}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`border-[1.5px] border-dashed ${borderCls} rounded-lg p-3 text-center transition-all ${
          !busy ? 'cursor-pointer hover:border-brand-primary hover:bg-brand-primary-muted' : ''
        }`}
      >
        {busy ? (
          <div className="flex flex-col items-center gap-2 py-1">
            {/* 阶段图标 */}
            <div className="relative">
              {stage === 'uploading' && (
                <svg className="animate-spin w-5 h-5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ color: 'var(--color-brand-primary)' }}>
                  <path d="M8 1.5a6.5 6.5 0 1 0 6.5 6.5" />
                </svg>
              )}
              {stage === 'ocr' && (
                <svg className="animate-pulse w-5 h-5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ color: 'var(--color-brand-primary)' }}>
                  <rect x="2" y="2" width="12" height="12" rx="1.5" />
                  <path d="M5 6h6M5 8.5h4M5 11h5" />
                </svg>
              )}
              {stage === 'llm' && (
                <svg className="animate-spin w-5 h-5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ color: 'var(--color-brand-primary)' }}>
                  <path d="M8 1.5a6.5 6.5 0 1 0 6.5 6.5" />
                  <path d="M5 6h6M5 8.5h4" />
                </svg>
              )}
            </div>

            {/* 阶段标签 + 耗时 */}
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-medium text-text-primary">{stageLabel}</span>
              <span className="text-[10px] text-text-muted">({fileCount} 文件)</span>
            </div>
            <span className="text-[10px] text-text-muted">{elapsed.toFixed(0)}s</span>

            {/* 进度条 */}
            <div className="w-full h-1.5 bg-bg-tertiary rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-300 ease-out"
                style={{
                  width: `${progress}%`,
                  background: 'linear-gradient(90deg, var(--color-brand-primary), var(--color-brand-secondary))',
                }}
              />
            </div>

            {/* 三阶段指示器 */}
            <div className="flex items-center gap-1 w-full">
              {STAGES.map((s, i) => (
                <div key={s.stage} className="flex items-center gap-1 flex-1">
                  <div
                    className={`w-1.5 h-1.5 rounded-full flex-shrink-0 transition-colors ${
                      stage === s.stage
                        ? 'bg-brand-primary'
                        : STAGES.findIndex((x) => x.stage === stage) > i
                          ? 'bg-brand-primary opacity-60'
                          : 'bg-border-default'
                    }`}
                  />
                  <span
                    className={`text-[9px] transition-colors ${
                      stage === s.stage
                        ? 'text-text-primary font-medium'
                        : 'text-text-muted'
                    }`}
                  >
                    {s.label}
                  </span>
                  {i < STAGES.length - 1 && (
                    <div className="flex-1 h-px bg-border-subtle mx-0.5" />
                  )}
                </div>
              ))}
            </div>

            {/* 提示文字 */}
            {stage === 'ocr' && elapsed > 30 && (
              <span className="text-[10px] text-text-muted">
                OCR 解析需要一些时间，请耐心等待...
              </span>
            )}
            {stage === 'ocr' && elapsed > 60 && (
              <span className="text-[10px] text-warning">
                耗时较长，可能因为图片较大或服务器繁忙
              </span>
            )}
          </div>
        ) : (
          <>
            <div className="mb-1 flex justify-center text-text-muted">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
            </div>
            <div className="text-xs font-medium text-text-secondary mb-0.5">
              {status === 'error' ? '分析失败，点击重试' : '拖入或点击上传职位文件'}
            </div>
            <div className={`text-xs ${status === 'error' ? 'text-error' : 'text-text-muted'}`}>
              {status === 'error' && errorMsg
                ? errorMsg
                : '截图 / PDF / TXT，支持多文件自动去重'}
            </div>
          </>
        )}
      </div>

      {/* 文件列表 */}
      {fileList.length > 0 && !busy && (
        <div className="space-y-1">
          {fileList.map((file, i) => (
            <div
              key={`${file.name}-${i}`}
              className="flex items-center gap-2 rounded-md bg-bg-secondary px-2 py-1.5"
            >
              <span className="text-sm flex-shrink-0">{getFileIcon(file.name)}</span>
              <span className="text-xs text-text-secondary truncate flex-1">{file.name}</span>
              <span className="text-[10px] text-text-muted flex-shrink-0">
                {(file.size / 1024).toFixed(0)}KB
              </span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  removeFile(i);
                }}
                className="text-text-muted hover:text-error flex-shrink-0 transition-colors"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          ))}
          {/* 开始分析按钮 */}
          <button
            onClick={handleAnalyze}
            className="w-full mt-1.5 rounded-md bg-brand-primary text-white text-xs font-medium py-2 hover:opacity-90 transition-opacity"
          >
            开始分析（{fileList.length} 个文件）
          </button>
        </div>
      )}

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        multiple
        onChange={handleInputChange}
        className="hidden"
      />
    </div>
  );
}
