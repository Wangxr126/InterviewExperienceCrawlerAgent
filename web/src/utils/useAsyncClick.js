import { ref } from 'vue';

/**
 * 防重复点击 + 异步执行的 Composable
 * @param {Function} asyncFn - 异步函数
 * @param {Object} options - 配置选项
 * @param {number} options.timeout - 超时时间（毫秒），默认 30000
 * @param {Function} options.onError - 错误回调
 * @returns {Object} { execute, isLoading }
 */
export function useAsyncClick(asyncFn, options = {}) {
  const isLoading = ref(false);
  const { timeout = 30000, onError } = options;

  const execute = async () => {
    // 防止重复点击
    if (isLoading.value) return;

    isLoading.value = true;
    let timeoutId = null;

    try {
      // 设置超时保护
      const timeoutPromise = new Promise((_, reject) => {
        timeoutId = setTimeout(() => {
          reject(new Error(`操作超时（${timeout}ms）`));
        }, timeout);
      });

      // 竞速：哪个先完成就用哪个结果
      await Promise.race([asyncFn(), timeoutPromise]);
    } catch (error) {
      console.error('异步操作失败:', error);
      onError?.(error);
    } finally {
      clearTimeout(timeoutId);
      isLoading.value = false;
    }
  };

  return {
    execute,
    isLoading,
  };
}
