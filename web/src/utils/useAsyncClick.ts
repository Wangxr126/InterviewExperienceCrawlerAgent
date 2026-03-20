import { ref } from 'vue';
import type { Ref } from 'vue';

/**
 * 异步操作的配置选项
 */
export interface UseAsyncClickOptions {
  /** 超时时间（毫秒），默认 30000 */
  timeout?: number;
  /** 错误回调函数 */
  onError?: (error: Error) => void;
}

/**
 * 防重复点击 + 异步执行的 Composable
 * @param asyncFn - 异步函数
 * @param options - 配置选项
 * @returns { execute, isLoading }
 */
export function useAsyncClick<T = void>(
  asyncFn: () => Promise<T>,
  options: UseAsyncClickOptions = {}
): {
  execute: () => Promise<void>;
  isLoading: Ref<boolean>;
} {
  const isLoading = ref(false);
  const { timeout = 30000, onError } = options;

  const execute = async (): Promise<void> => {
    // 防止重复点击
    if (isLoading.value) return;

    isLoading.value = true;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    try {
      // 设置超时保护
      const timeoutPromise = new Promise<never>((_, reject) => {
        timeoutId = setTimeout(() => {
          reject(new Error(`操作超时（${timeout}ms）`));
        }, timeout);
      });

      // 竞速：哪个先完成就用哪个结果
      await Promise.race([asyncFn(), timeoutPromise]);
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      console.error('异步操作失败:', err);
      onError?.(err);
    } finally {
      if (timeoutId) clearTimeout(timeoutId);
      isLoading.value = false;
    }
  };

  return {
    execute,
    isLoading,
  };
}
