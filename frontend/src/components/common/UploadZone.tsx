// frontend/src/components/common/UploadZone.tsx
// 拖拽上传区
// - 当传入 onFileUploaded 时为交互式上传组件（拖拽 / 点击选择 / 上传 → [可选解析] → 回调）
// - 否则退化为静态可点击占位（用于知识素材等暂不接后端的入口）
//
// 支持两种上传流水线：
// 1. 简历模式（默认）：uploadResume(file) → parseResume(id) → onFileUploaded(ParseResponse)
// 2. 知识库模式：传入 uploadFn=uploadKnowledge + parseFn=null，
//    仅执行 uploadFn → onFileUploaded({ id, ... })

import { useRef, useState } from 'react';
import { parseResume, uploadResume } from '@/lib/api';
import type { ParseResponse } from '@/types/resume';

/** 上传状态机 */
type UploadStatus = 'idle' | 'uploading' | 'parsing' | 'success' | 'error';

/** 上传函数返回的最小契约：至少包含 id（用于后续解析） */
type UploadResult = { id: string };

interface UploadZoneProps {
  title: string;
  hint: string;
  icon?: React.ReactNode;
  /** 静态模式下的点击回调（onFileUploaded 未传时生效） */
  onClick?: () => void;
  /**
   * 交互模式回调：上传（+解析）成功后触发。
   * 简历模式收到 ParseResponse；知识库模式收到 uploadFn 的返回值。
   */
  onFileUploaded?: (result: ParseResponse | UploadResult) => void;
  /** 允许的文件类型，默认 PDF / Word */
  accept?: string;
  /** 自定义上传函数。未传时使用默认 uploadResume */
  uploadFn?: (file: File) => Promise<UploadResult>;
  /**
   * 自定义解析函数。未传时使用默认 parseResume；
   * 传 null 则跳过解析步骤（知识库模式）。
   */
  parseFn?: ((uploadId: string) => Promise<ParseResponse>) | null;
  /** 成功提示文案，默认 "已生成版本树节点" */
  successText?: string;
  /** 文件类型不匹配时的提示文案 */
  invalidTypeMessage?: string;
}

/** 状态 → 展示文案 */
const STATUS_TEXT: Record<UploadStatus, string> = {
  idle: '拖入旧简历',
  uploading: '上传中...',
  parsing: 'AI 解析中...',
  success: '✓ 解析完成',
  error: '✗ 解析失败',
};

const DEFAULT_ACCEPT = '.pdf,.docx';

function isValidResumeFile(file: File, accept: string): boolean {
  const exts = accept
    .split(',')
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
  const name = file.name.toLowerCase();
  return exts.some((ext) => name.endsWith(ext));
}

export default function UploadZone({
  title,
  hint,
  icon,
  onClick,
  onFileUploaded,
  accept = DEFAULT_ACCEPT,
  uploadFn,
  parseFn,
  successText = '已生成版本树节点',
  invalidTypeMessage = '仅支持 PDF / Word 文件',
}: UploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<UploadStatus>('idle');
  const [isDragging, setIsDragging] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const interactive = Boolean(onFileUploaded);
  const busy = status === 'uploading' || status === 'parsing';
  const skipParse = parseFn === null;

  /** 处理单个文件：上传 → [可选解析] → 回调 */
  async function handleFile(file: File) {
    if (!isValidResumeFile(file, accept)) {
      setStatus('error');
      setErrorMsg(invalidTypeMessage);
      return;
    }

    setStatus('uploading');
    setErrorMsg(null);
    try {
      const upload = uploadFn ? await uploadFn(file) : await uploadResume(file);

      // 知识库模式（parseFn === null）跳过解析
      if (skipParse) {
        setStatus('success');
        onFileUploaded?.(upload);
        return;
      }

      setStatus('parsing');
      const parseRes = parseFn ? await parseFn(upload.id) : await parseResume(upload.id);
      setStatus('success');
      onFileUploaded?.(parseRes);
    } catch (err) {
      setStatus('error');
      setErrorMsg(err instanceof Error ? err.message : '解析失败，请重试');
    }
  }

  function openPicker() {
    if (!interactive || busy) return;
    inputRef.current?.click();
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) void handleFile(file);
    // 重置 value 以便重复选择同一文件
    e.target.value = '';
  }

  function handleDragOver(e: React.DragEvent) {
    if (!interactive || busy) return;
    e.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave(e: React.DragEvent) {
    if (!interactive) return;
    e.preventDefault();
    setIsDragging(false);
  }

  function handleDrop(e: React.DragEvent) {
    if (!interactive || busy) return;
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) void handleFile(file);
  }

  // 状态色：成功 success / 失败 error / 进行中 text-muted
  const statusColor =
    status === 'success'
      ? 'text-success'
      : status === 'error'
        ? 'text-error'
        : 'text-text-muted';

  const showStatusText = status !== 'idle';
  const borderCls = isDragging
    ? 'border-brand-primary bg-brand-primary-muted'
    : 'border-border-default';

  return (
    <div
      onClick={interactive ? openPicker : onClick}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`border-[1.5px] border-dashed ${borderCls} rounded-lg p-4 text-center transition-all ${
        !busy ? 'cursor-pointer hover:border-brand-primary hover:bg-brand-primary-muted' : ''
      }`}
    >
      <div className="mb-2 opacity-50 flex justify-center text-text-muted">
        {icon ?? (
          <svg
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          >
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        )}
      </div>

      <div className="text-xs font-medium text-text-secondary mb-1">
        {showStatusText ? STATUS_TEXT[status] : title}
      </div>

      <div className={`text-xs ${showStatusText ? statusColor : 'text-text-muted'}`}>
        {showStatusText
          ? status === 'error' && errorMsg
            ? errorMsg
            : status === 'success'
              ? successText
              : hint
          : hint}
      </div>

      {interactive && (
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          onChange={handleInputChange}
          className="hidden"
        />
      )}
    </div>
  );
}
