import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  calculatePageHeight,
  calculateTotalPages,
  isPageOverflow,
  calculatePageBreakPositions,
  A4_ASPECT_RATIO,
} from '../src/lib/pagination.ts';

test('calculatePageHeight accurately maps container width to A4 aspect ratio', () => {
  assert.equal(calculatePageHeight(0), 0);
  assert.equal(calculatePageHeight(-100), 0);

  // A4 标准宽度 794px 对应高度应为约 1123px (794 * 1.41421356 = 1122.88)
  assert.equal(calculatePageHeight(794), 1123);

  // max-w-2xl 容器 (672px): 672 * 1.41421356 = 950.35 -> 950
  assert.equal(calculatePageHeight(672), 950);
});

test('calculateTotalPages returns at least 1 and calculates boundaries correctly', () => {
  const pageHeight = 1000;

  // 异常/空值兜底
  assert.equal(calculateTotalPages(0, pageHeight), 1);
  assert.equal(calculateTotalPages(500, 0), 1);

  // 单页内
  assert.equal(calculateTotalPages(500, pageHeight), 1);
  assert.equal(calculateTotalPages(1000, pageHeight), 1);

  // 刚好溢出 1px -> 2 页
  assert.equal(calculateTotalPages(1001, pageHeight), 2);
  assert.equal(calculateTotalPages(2000, pageHeight), 2);

  // 3 页
  assert.equal(calculateTotalPages(2001, pageHeight), 3);
});

test('isPageOverflow checks against target page count', () => {
  // 目标 1 页
  assert.equal(isPageOverflow(1, 1), false);
  assert.equal(isPageOverflow(2, 1), true);

  // 目标 2 页
  assert.equal(isPageOverflow(1, 2), false);
  assert.equal(isPageOverflow(2, 2), false);
  assert.equal(isPageOverflow(3, 2), true);
});

test('calculatePageBreakPositions returns positions for multi-page resumes', () => {
  const pageHeight = 1000;

  // 单页不生成分页截断线
  assert.deepEqual(calculatePageBreakPositions(pageHeight, 1), []);

  // 2 页生成 1 条分页线 (位于 1000px 处)
  assert.deepEqual(calculatePageBreakPositions(pageHeight, 2), [1000]);

  // 3 页生成 2 条分页线 (位于 1000px 与 2000px 处)
  assert.deepEqual(calculatePageBreakPositions(pageHeight, 3), [1000, 2000]);
});
