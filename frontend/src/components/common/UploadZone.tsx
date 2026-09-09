// frontend/src/components/common/UploadZone.tsx
// 拖拽上传区
// - 当传入 onFileUploaded 时为交互式上传组件（拖拽 / 点击选择 / 上传 → [可选解析] → 回调）
// - 否则退化为静态可点击占位（用于知识素材等暂不接后端的入口）
//
// 支持两种上传流水线：
// 1. 简历模式（默认）：uploadResume(file) → 提取 → 用户确认 → onFileUploaded(ParseResponse)
// 2. 知识库模式：传入 uploadFn=uploadKnowledge + parseFn=null，
//    仅执行 uploadFn → onFileUploaded({ id, ... })

import { useEffect, useRef, useState } from 'react';
import { getParseTask, startParseResume, streamParseTaskEvents, uploadResume } from '@/lib/api';
import ParseConfirmModal from './ParseConfirmModal';
import type { ParseResponse, ParseTaskDetail } from '@/types/resume';

/** 上传状态机 */
type UploadStatus = 'idle' | 'uploading' | 'parsing' | 'confirming' | 'success' | 'error';

/** 上传函数返回的最小契约：包含 upload_id 或 id（用于后续解析） */
type UploadResult = { upload_id?: string; id?: string };

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
   * 自定义解析函数。未传时使用默认两阶段解析；
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
  confirming: '等待确认解析结果',
  success: '✓ 已完成',
  error: '✗ 解析失败',
};

const PENDING_TASK_KEY = 'resume-agent:pending-parse-task';
function rememberTask(id: string | null) {
  try { if (id) localStorage.setItem(PENDING_TASK_KEY, id); else localStorage.removeItem(PENDING_TASK_KEY); } catch { /* 浏览器禁用存储时仍可完成当前流程 */ }
}

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

  const [task, setTask] = useState<ParseTaskDetail | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [progress, setProgress] = useState('正在读取文件…');
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [warning, setWarning] = useState('');
  const controller = useRef<AbortController | null>(null);
  const inFlight = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    if (onFileUploaded && parseFn === undefined) {
      let id: string | null = null;
      try { id = localStorage.getItem(PENDING_TASK_KEY); } catch { /* 无持久化时跳过恢复 */ }
      if (id) void resumeTask(id);
    }
    return () => { mounted.current = false; controller.current?.abort(); };
  // 仅挂载时恢复任务；调用方回调会随页面渲染改变。
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function resumeTask(id: string) {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    setPendingId(id); rememberTask(id);
    setStatus('parsing'); setErrorMsg(null);
    setProgress('正在获取解析结果…');
    void streamParseTaskEvents(id, { signal: current.signal, onEvent: (event) => {
      if (current.signal.aborted) return;
      if (event.type === 'status') setProgress('正在读取简历文件…');
      if (event.type === 'file_parsed') setProgress(event.degraded ? '已降级为本地解析，正在整理字段…' : '文件读取完成，正在整理字段…');
      if (event.type === 'extracting') setProgress('AI 正在提取字段，请稍候…');
    }}).catch(() => { if (!current.signal.aborted) setProgress('进度连接中断，正在轮询获取结果…'); });
    try {
      while (!current.signal.aborted) {
        const detail = await getParseTask(id);
        if (current.signal.aborted) return;
        if (detail.status === 'failed') throw new Error(detail.error || '解析失败，请重新解析');
        if (detail.status === 'confirmed') {
          rememberTask(null); setPendingId(null); setTask(null); setStatus('success');
          return;
        }
        if (detail.status === 'awaiting_confirm') {
          if (!detail.structured_resume) throw new Error('解析结果缺失，请重新解析');
          setTask(detail); setModalOpen(true); setStatus('confirming');
          return;
        }
        await new Promise<void>((resolve) => {
          const done = () => { clearTimeout(timer); current.signal.removeEventListener('abort', done); resolve(); };
          const timer = setTimeout(done, 1200);
          current.signal.addEventListener('abort', done, { once: true });
        });
      }
    } catch (err) {
      if (!current.signal.aborted) {
        setStatus('error'); setErrorMsg(err instanceof Error ? err.message : '获取解析结果失败');
      }
    } finally { current.abort(); }
  }

  async function retryTask() {
    if (!pendingId || inFlight.current) return;
    inFlight.current = true;
    setStatus('parsing'); setErrorMsg(null);
    try {
      const detail = await getParseTask(pendingId);
      const id = detail.status === 'failed' ? (await startParseResume(detail.upload_id)).task_id : pendingId;
      if (mounted.current) await resumeTask(id);
    } catch (err) {
      if (mounted.current) { setStatus('error'); setErrorMsg(err instanceof Error ? err.message : '重试失败'); }
    } finally { inFlight.current = false; }
  }

  function confirmed(result: ParseResponse) {
    rememberTask(null); setPendingId(null); setModalOpen(false); setTask(null);
    setStatus('success'); setWarning(result.knowledge_warning ?? '');
    onFileUploaded?.(result);
  }

  const interactive = Boolean(onFileUploaded);
  const busy = status === 'uploading' || status === 'parsing' || status === 'confirming';
  const skipParse = parseFn === null;

  /** 处理单个文件：上传 → [可选解析] → 回调 */
  async function handleFile(file: File) {
    if (inFlight.current || busy) return;
    if (!isValidResumeFile(file, accept)) {
      setStatus('error');
      setErrorMsg(invalidTypeMessage);
      return;
    }

    inFlight.current = true;
    setWarning('');
    setStatus('uploading');
    setErrorMsg(null);
    try {
      const upload = uploadFn ? await uploadFn(file) : await uploadResume(file);

      if (!mounted.current) return;

      // 知识库模式（parseFn === null）跳过解析
      if (skipParse) {
        setStatus('success');
        onFileUploaded?.(upload);
        return;
      }

      setStatus('parsing');
      const uploadId = ('upload_id' in upload ? upload.upload_id : (upload as { id?: string }).id) ?? '';
      if (parseFn) {
        const parseRes = await parseFn(uploadId);
        if (mounted.current) { setStatus('success'); onFileUploaded?.(parseRes); }
      } else {
        const started = await startParseResume(uploadId);
        rememberTask(started.task_id);
        if (mounted.current) await resumeTask(started.task_id);
      }
    } catch (err) {
      if (!mounted.current) return;
      setStatus('error');
      setErrorMsg(err instanceof Error ? err.message : '解析失败，请重试');
    } finally { inFlight.current = false; }
  }

  function openPicker() {
    if (status === 'confirming') { setModalOpen(true); return; }
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
    <>
    <div
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      aria-disabled={busy && status !== 'confirming'}
      onKeyDown={(e) => { if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); openPicker(); } }}
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
        {showStatusText ? (status === 'parsing' ? progress : STATUS_TEXT[status]) : title}
      </div>

      <div className={`text-xs ${showStatusText ? statusColor : 'text-text-muted'}`}>
        {showStatusText
          ? status === 'error' && errorMsg
            ? errorMsg
            : status === 'success'
              ? successText
              : status === 'confirming' ? '点击继续确认；尚未入库' : hint
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
    {status === 'error' && pendingId && <button type="button" className="min-h-10 rounded-md border border-border-default px-3 py-2 text-sm text-brand-primary" onClick={() => void retryTask()}>重试解析 / 恢复结果</button>}
    {warning && <p role="alert" className="text-sm text-warning">{warning}</p>}
    {task && <ParseConfirmModal key={task.task_id} task={task} open={modalOpen} onClose={() => setModalOpen(false)} onConfirmed={confirmed} />}
    </>
  );
}
