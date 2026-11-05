# feature/player-vs-player → need-review

Ngày kiểm tra: 2026-10-30. **Verdict: DO NOT MERGE nguyên nhánh cho mục tiêu lấy PvP.**

Tên user cung cấp ban đầu là `final/playervsplayer`; không tìm thấy ref chính xác trên origin/upstream. User đã xác nhận nhánh cần xem là `origin/feature/player-vs-player`, cùng với `origin/feature/nguoivsnguoifinal`. Lựa chọn donor đã được xác nhận; không merge. Các SHA và kết quả kiểm tra giữ nguyên.

- Donor SHA: `75c1bc9485eafa42aed3b04ffaf1d822b42ef757`.
- Target giả định: nhánh đang làm việc `need-review`, committed SHA `18e67fc9006a91a2a32c4c861974760089a687de`, cộng kiểm tra tương thích source chưa commit.
- Merge base: `e6bb6323a966727de1a17e57625711b3c2ead0c3`.
- Divergence: donor 29 commit riêng, target 147 commit riêng.
- Working tree có nhiều thay đổi chưa commit; được bảo toàn.

**VERIFIED:** tip `75c1bc9` là `Revert "feat: add local two-player Xiangqi mode"`, parent là commit đã thêm PvP `93fef3a`. `git diff fb0598d origin/feature/player-vs-player` rỗng: so với parent trước feature, tip không còn code PvP. Đây là trạng thái Git thực tế, không phải phỏng đoán từ tên nhánh.

Mô phỏng `git merge-tree --write-tree HEAD origin/feature/player-vs-player` trả exit 1, 32 file conflict. Ghép nhánh này với `feature/nguoivsnguoifinal` còn có modify/delete conflict ở `player_vs_player.py` do một nhánh revert, một nhánh tiếp tục sửa.

Không có phần PvP cần lấy từ tip. Những thay đổi visual/setup kế thừa trong primary diff cần review theo phạm vi riêng nếu muốn lấy; không dùng nhánh này để thay runtime/config/calibration hiện tại. Các xung đột và implementation legacy tạo rủi ro mất authority/worker/fresh-start/user-0 đang có nếu chọn toàn bộ source donor.

Review-only: không sửa production, không checkout/merge/cherry-pick, không điều khiển hardware. CI/full donor runtime/full regression: NOT RUN hoặc NOT AVAILABLE. Metadata và raw diffs được giữ trong [thư mục bằng chứng](pvp-20261030/metadata.json); mô phỏng [merge-tree](pvp-20261030/player_vs_head.merge-tree.txt).

Phân tích tính năng còn hiệu lực ở donor thứ hai, phát hiện BLOCKER/HIGH, 13 probe donor và 45 test current được trình bày trong [báo cáo tích hợp chính](feature-nguoivsnguoifinal_vs_need-review_REVIEW_REPORT.md). Báo cáo đó phân biệt inherited code, new PvP entrypoints và semantic integration conflicts; không coi mọi thay đổi cũ là do commit mới.
