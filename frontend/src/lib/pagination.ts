// frontend/src/lib/pagination.ts
// US-34 预览分页计算核心逻辑

/**
 * A4 纸张标准宽高比：1 : √2 (297mm / 210mm ≈ 1.41421356)
 */
export const A4_ASPECT_RATIO = 1.41421356;

/**
 * 根据容器实际渲染宽度计算 A4 单页像素高度
 *
 * @param containerWidth 容器宽度 (px)
 * @returns 单页基准高度 (px)
 */
export function calculatePageHeight(containerWidth: number): number {
  if (!containerWidth || containerWidth <= 0) return 0;
  return Math.round(containerWidth * A4_ASPECT_RATIO);
}

/**
 * 根据总内容高度与单页高度计算总页数
 *
 * @param contentHeight 内容实际高度 (px)
 * @param pageHeight 单页基准高度 (px)
 * @returns 计算后的总页数 (至少为 1)
 */
export function calculateTotalPages(contentHeight: number, pageHeight: number): number {
  if (!pageHeight || pageHeight <= 0 || !contentHeight || contentHeight <= 0) {
    return 1;
  }
  return Math.max(1, Math.ceil(contentHeight / pageHeight));
}

/**
 * 校验当前页数是否超出目标页数
 *
 * @param totalPages 实际总页数
 * @param targetPages 目标页数 (默认 1)
 * @returns 是否溢出
 */
export function isPageOverflow(totalPages: number, targetPages: number): boolean {
  if (!targetPages || targetPages <= 0) return false;
  return totalPages > targetPages;
}

/**
 * 计算所有 A4 分页截断线在容器中的绝对 Y 轴坐标
 *
 * @param pageHeight 单页基准高度 (px)
 * @param totalPages 实际总页数
 * @returns 每页末尾截断线的 Y 轴像素位置数组
 */
export function calculatePageBreakPositions(pageHeight: number, totalPages: number): number[] {
  if (!pageHeight || pageHeight <= 0 || !totalPages || totalPages <= 1) {
    return [];
  }
  const positions: number[] = [];
  for (let i = 1; i < totalPages; i++) {
    positions.push(i * pageHeight);
  }
  return positions;
}
