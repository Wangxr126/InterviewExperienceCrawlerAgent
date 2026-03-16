/**
 * 评分弹窗管理 Composable
 * 功能：
 * 1. 弹出评分框
 * 2. 等待用户评分
 * 3. 提交评分后异步处理（不阻塞 UI）
 */

import { ref } from 'vue';
import { ElMessageBox } from 'element-plus';

/**
 * 评分弹窗状态管理
 */
export function useRatingDialog() {
  const ratingVisible = ref(false);
  const currentRating = ref(0);
  const ratingComment = ref('');

  /**
   * 弹出评分框，等待用户评分
   * @returns {Promise<{rating: number, comment: string}>} 用户的评分和评论
   */
  const showRatingDialog = () => {
    return new Promise((resolve, reject) => {
      ElMessageBox.confirm(
        `
          <div style="text-align: center; padding: 20px 0;">
            <div style="font-size: 16px; margin-bottom: 20px; font-weight: 600;">
              请评分这次回答的质量
            </div>
            <div style="display: flex; justify-content: center; gap: 10px; margin-bottom: 20px;">
              ${[1, 2, 3, 4, 5]
                .map(
                  (star) => `
                <button 
                  class="rating-star" 
                  data-rating="${star}"
                  style="
                    font-size: 32px;
                    background: none;
                    border: none;
                    cursor: pointer;
                    opacity: 0.5;
                    transition: all 0.2s;
                  "
                  onmouseover="this.style.opacity='1'; this.style.transform='scale(1.2)'"
                  onmouseout="this.style.opacity='0.5'; this.style.transform='scale(1)'"
                >
                  ⭐
                </button>
              `
                )
                .join('')}
            </div>
            <textarea 
              id="rating-comment"
              placeholder="（可选）请输入你的评论..."
              style="
                width: 100%;
                height: 80px;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
                resize: none;
              "
            ></textarea>
          </div>
        `,
        '评分',
        {
          confirmButtonText: '提交',
          cancelButtonText: '取消',
          dangerouslyUseHTMLString: true,
          beforeClose: (action, instance, done) => {
            if (action === 'confirm') {
              const selectedStar = document.querySelector('.rating-star.selected');
              const rating = selectedStar ? parseInt(selectedStar.dataset.rating) : 0;
              const comment = document.getElementById('rating-comment')?.value || '';

              if (rating === 0) {
                ElMessage.warning('请选择评分');
                return;
              }

              resolve({ rating, comment });
              done();
            } else {
              reject(new Error('用户取消评分'));
              done();
            }
          },
        }
      ).then(() => {
        // 处理星星点击
        setTimeout(() => {
          const stars = document.querySelectorAll('.rating-star');
          stars.forEach((star) => {
            star.addEventListener('click', function () {
              stars.forEach((s) => s.classList.remove('selected'));
              this.classList.add('selected');
              // 更新所有星星的样式
              stars.forEach((s) => {
                if (parseInt(s.dataset.rating) <= parseInt(this.dataset.rating)) {
                  s.style.opacity = '1';
                } else {
                  s.style.opacity = '0.5';
                }
              });
            });
          });
        }, 0);
      });
    });
  };

  return {
    ratingVisible,
    currentRating,
    ratingComment,
    showRatingDialog,
  };
}

/**
 * 完整的评分流程：弹窗 → 等待 → 提交
 * @param {Function} onRatingSubmit - 评分提交后的回调（异步）
 * @returns {Promise<void>}
 */
export async function handleRatingFlow(onRatingSubmit) {
  const { showRatingDialog } = useRatingDialog();

  try {
    // 1. 弹出评分框，等待用户操作
    const { rating, comment } = await showRatingDialog();

    // 2. 用户提交后，异步处理（不阻塞 UI）
    // 这里不用 await，让它在后台执行
    onRatingSubmit?.(rating, comment).catch((err) => {
      console.error('评分提交失败:', err);
    });

    // 3. 立即返回，不等待后台任务完成
    return;
  } catch (err) {
    console.log('评分被取消或出错:', err.message);
  }
}
