# Guideline Road v1.0 · AI20K K5 · Ngày 11

Đây là guideline do khóa học soạn để gán nhãn phần tử đường. Nó không phải guideline chính thức của BDD100K hay WoodScape: hai bộ dữ liệu đó chỉ cung cấp ảnh (và nhãn nền cho coach). Khi guideline này khác cách gán gốc của dataset, bạn làm theo guideline này.

Đọc ở đâu: bài giảng sáng, slide 28–42 (làn, vùng lái, đèn, biển) và slide 55–58 (fisheye); phần này; slide 9–10 của deck thực hành. Ngày 20 mở rộng thành phiên bản 1.x (ô đỗ, ca mưa, đêm); mã và nghĩa các quy tắc dưới đây không đổi. Bản máy đọc cho script: [`lab/AGENTS.md`](../lab/AGENTS.md).

## Thẻ đặc tả

| Mục | Nội dung |
| --- | --- |
| Phiên bản | Road v1.0 (mã quy tắc QC1-01 đến QC1-12) |
| Phạm vi | Ảnh camera trước (front) và bốn camera fisheye; sáu label và bốn tag ở mục 1. Tag ghi được đêm, mưa, sương, nhưng quy tắc vẽ là một bộ cho mọi điều kiện |
| Ngoài phạm vi | Ô đỗ và quy tắc riêng cho ca mưa, đêm (Road v1.x, Ngày 20); xe, người đi bộ, vật cản; ảnh fisheye đã nắn |
| Người giữ guideline | Lab Coach Ngày 11; câu hỏi chưa có trong guideline ghi vào bảng ca khó và hỏi lead |
| Đầu ra | CVAT for images 1.1 kèm manifest bàn giao, xem [đặc tả bàn giao](delivery_road_v1.0.md) |
| Kiểm chất lượng | Phiếu QC 1 với thang nặng / chính / nhẹ, xem [thang mức lỗi](qc_severity_road_v1.0.md) |
| Đổi phiên bản | Đổi nghĩa một quy tắc thì tăng số phiên bản và ghi vào lịch sử dưới đây; bài đã gán theo bản cũ ghi rõ bản cũ |

Lịch sử: v1.0 (Ngày 11, K5) bản đầu. Mẫu thẻ này lấy ý từ guideline gán nhãn công khai của các bộ dữ liệu xe tự hành (nuScenes, Zenseact ZOD): mỗi label có định nghĩa, quy tắc riêng và ví dụ ca khó.

## 1. Gán gì, vẽ hình gì, dạng gì

| Label | Dạng trong CVAT | Vẽ cái gì trên ảnh | Thuộc tính |
| --- | --- | --- | --- |
| `lane` | polyline (đường gấp khúc, hở) | Một vạch kẻ làn: nối các điểm nằm trên tâm vệt sơn, từ gần xe ra xa | position L1, R1, L2, R2, other · style solid, dashed · color white, yellow, other · kind single, double |
| `road_curb` | polyline | Mép đường là vỉa hè hoặc lề, nơi không có vạch sơn | không có |
| `crosswalk` | polygon (vùng kín) | Cả vùng vạch ngựa vạn, một polygon bao các vạch | không có |
| `drivable` | polygon | Phần mặt đường xe đi được nếu đường trống | area_type direct (làn đang đi, không gồm dải đỗ xe sát lề), alternative (làn cùng chiều bên cạnh) |
| `traffic_light` | rectangle (hộp chữ nhật) | Cả vỏ cụm đèn, hộp sát mép | color red, yellow, green, off, unknown · type vehicle, pedestrian, beacon · facing front, side, back · edge_zone (ô tick) |
| `traffic_sign` | rectangle | Cả tấm biển, hộp sát mép (biển phụ có hộp riêng) | group prohibitory, mandatory, warning, information, supplementary, other · facing front, side, back · edge_zone |
| Tag ảnh | tag (nhãn cho cả ảnh, không vẽ hình) | Gắn cho mỗi ảnh một lần | camera front, fisheye_front, fisheye_rear, fisheye_left, fisheye_right · timeofday day, dusk, night · weather clear, overcast, rain, fog, other · source real, simulated |

Cờ occluded có sẵn trong CVAT: bật cho đoạn polyline bạn nối qua chỗ bị che.

Trên CVAT của lớp, mỗi tag ảnh là một label kiểu Tag có một thuộc tính select tên `value` (ví dụ label `camera`, thuộc tính `value` = `fisheye_left`).

## 2. Thứ tự làm trên mỗi ảnh

1. Bốn tag ảnh (camera trước tiên).
2. Làn: R1 và L1, rồi L2 và R2 nếu thấy; road_curb nếu mép đường không sơn.
3. Thuộc tính của từng vạch; bật occluded nếu có đoạn nối qua chỗ che.
4. drivable (direct, rồi alternative nếu có); crosswalk nếu có.
5. Hộp đèn và biển, đủ thuộc tính.
6. Ctrl+S.

Mỗi ảnh chỉ yêu cầu nhóm label ghi ở bảng kế hoạch ảnh (slide Task 1, Task 2 của deck thực hành); không gán những loại không được yêu cầu cho ảnh đó.

## 3. Quy tắc

### Làn (lane)

- Polyline đặt trên tâm vệt sơn, không đặt ở mép vạch.
- Vẽ từ gần xe ra xa. Điểm đầu sát xe là điểm quan trọng nhất, đặt thật chính xác.
- Vạch đứt là một polyline, không phải mỗi vệt một đường.
- Đoạn bị che ngắn (xe, người): nối liền qua chỗ che và bật occluded. Đừng dừng trước vật che.
- Dừng ở điểm xa nhất còn thấy vạch, không kéo tới chân trời.
- Lệch khỏi tâm vạch tối đa 5 px. Thêm điểm ở chỗ vạch cong.
- position tính theo làn đang đi: L1 và R1 là hai vạch sát xe, L2 và R2 là vạch kế tiếp bên ngoài.

### Vùng lái (drivable)

Gán theo "đi được nếu đường trống", không khoét lỗ quanh xe khác. Không gồm lề, vỉa hè, thân xe mình, vùng phía sau cọc. Dải đỗ xe sát lề cũng không tính vào `direct`: đó là vùng có chức năng khác (dừng, đỗ), không phải làn đang đi, kể cả khi lúc chụp không có xe đỗ.

### Tag weather

- `clear`: trời quang hoặc ít mây, mặt đường khô.
- `overcast`: trời âm u, nhiều mây nhưng khô, không mưa, không sương.
- `rain`: đang mưa hoặc mặt đường ướt rõ do mưa. `fog`: sương mù, khói bụi làm giảm tầm nhìn. `other`: tuyết hoặc trường hợp không xếp được, ghi vào bảng ca khó.

### Đèn và biển

- Gán mọi cụm đèn và tấm biển cao từ 8 px trở lên.
- Hộp sát vỏ đèn hoặc mép biển, không gồm cần treo.
- color của đèn là màu đang sáng trong ảnh này; đèn tắt là off.
- Biển phụ (tấm nhỏ dưới biển chính) có hộp riêng, group = supplementary.
- Hình biển in trên thùng xe, ảnh phản chiếu không phải biển: không gán.

### Nhóm biển (group) cho biển trong ảnh BDD100K (biển Mỹ)

Ảnh BDD100K quay ở Mỹ nên hình dạng và màu biển khác biển Việt Nam (QCVN 41:2024/BGTVT). Bạn phân nhóm theo chức năng của biển, không theo hình dạng hay màu. Năm nhóm này tương ứng năm nhóm của quy chuẩn Việt Nam.

| group | Tương ứng ở Việt Nam | Biển Mỹ thường gặp trong ảnh |
| --- | --- | --- |
| prohibitory | biển cấm | Stop, Yield, Speed Limit, Do Not Enter, Wrong Way, No Left Turn, No U-Turn, No Parking, No Trucks |
| mandatory | biển hiệu lệnh | One Way, Keep Right, Keep Left, Left Turn Only, Straight Only (biển bắt buộc đi theo hướng) |
| warning | biển nguy hiểm và cảnh báo | hình thoi vàng (đường cong, giao lộ, đèn tín hiệu phía trước, người đi bộ qua đường, trường học); biển công trường màu cam |
| information | biển chỉ dẫn | biển xanh lá chỉ hướng và lối ra, biển số đường (route shield), biển xanh dương dịch vụ (bệnh viện, trạm xăng) |
| supplementary | biển phụ | tấm chữ nhật nhỏ đi kèm biển chính ("SCHOOL", "XING", mũi tên, "500 FT", thời gian, "EXCEPT ...") |
| other | không thuộc năm nhóm | chỉ dùng khi không xếp được; ghi vào bảng ca khó |

Biển không chắc nhóm: chọn nhóm gần nhất theo chức năng, ghi vào bảng ca khó kèm lý do; coach không trừ điểm khi lý do hợp lý.

## 4. Riêng ảnh fisheye (camera bắt đầu bằng fisheye_)

- Polyline đi theo cung cong trên ảnh; vạch thẳng ngoài đời thành cong trên ảnh. Không nối hai điểm đầu cuối, không nắn ảnh. Mọi chỗ lệch ≤ 5 px, đặt điểm dày ở vòng ngoài nơi cung cong nhất.
- Thân xe mình và vùng tối viền ảnh: không gán, và không tính vào vùng lái.
- position L1/R1/L2/R2 chỉ dùng ở fisheye_front và fisheye_rear. Ở fisheye_left và fisheye_right luôn dùng position = other.
- Đèn, biển có tâm hộp nằm ngoài 80 % bán kính vòng ảnh: bật edge_zone. Hộp vẫn thẳng, sát pixel, ôm cả phần nền ở các góc.
- Vạch ngựa vạn gán crosswalk (polygon). Vạch ô đỗ không gán lane.

## 5. Kiểm trước khi nộp (self-QC)

- [ ] Mọi ảnh đủ bốn tag, camera đúng.
- [ ] Mọi polyline đi từ gần ra xa, vạch đứt là một đường, chỗ che có occluded.
- [ ] Không còn L1 hoặc R1 bị thiếu khi thấy được; không nhầm L1 với L2.
- [ ] Hộp đèn, biển sát và đủ thuộc tính.
- [ ] Ảnh fisheye: theo cung, không gán thân xe.
- [ ] Export CVAT for images 1.1 và mở lại được (`python -m road_lab.road_check lint <file>.zip`).
- [ ] Tạo manifest bàn giao bằng `lint --manifest` với `--revision 1` (lần đầu) hoặc `2` (sau Rework); giữ tên zip, giữ manifest của lần trước.

## 6. Liên hệ thực tế (đọc thêm, không đổi quy tắc ở trên)

Phần này nối guideline với tài liệu ngoài để bạn biết các quy tắc trên đến từ đâu. Nó không thêm quy tắc chấm mới. Khóa học không tuyên bố bài lab tuân thủ ISO, QCVN hay chuẩn doanh nghiệp nào; mỗi dự án thật có guideline, ngưỡng và thang mức lỗi riêng.

**Vạch kẻ đường Việt Nam (QCVN 41:2024/BGTVT, Phụ lục G).** Ảnh của lab là ảnh Mỹ, nhưng quy ước màu giống nhau:

| Nhóm vạch QCVN | Ví dụ | Màu | Ứng với thuộc tính `lane` |
| --- | --- | --- | --- |
| 1.x phân chia hai chiều xe chạy (tim đường) | 1.1 đứt, 1.2 liền, 1.3 đôi liền | vàng | color yellow; 1.3 là kind double |
| 2.x phân chia các làn cùng chiều | 2.1 đứt, 2.2 liền | trắng | color white |
| 3.1 mép ngoài phần đường xe chạy | | trắng | lane (position theo làn), không phải road_curb |

Vạch đôi một liền một đứt (QCVN 1.4) không có giá trị style riêng trong Road v1.0: ghi vào bảng ca khó, nêu nửa nào bạn chọn.

**Tag ảnh và điều kiện vận hành (ODD).** Tag `timeofday` và `weather` là hai yếu tố trong nhóm điều kiện môi trường của ISO 34503 (chiếu sáng; thời tiết; sương, bụi). Nhờ tag, người làm dữ liệu đếm được bộ ảnh có đủ ca đêm, ca mưa hay chưa. Gán sai tag (ví dụ ảnh trời khô gán rain) là một ví dụ lỗi nhãn mà ISO/PAS 8800 (Điều 11) nêu cho dữ liệu AI trên ô tô.

**Loại lỗi trên Phiếu QC 1.** ISO/IEC 5259-4 (mục 8.4.2) chia lỗi gán nhãn thành ba loại: bỏ sót (thiếu nhãn phải có), thừa (gán cái không phải đối tượng), sai phạm vi (hình lệch, dừng sớm, tràn vùng). Cột "Loại lỗi" trên phiếu dùng ba loại này, thêm "sai thuộc tính" và "lỗi file" của khóa học.

**Quy trình kiểm.** Chu trình của lab (tự kiểm → bạn khác kiểm → Release / Hold / Rework → sửa và nộp lại) giống mô tả ở ISO/IEC 5259-4 mục 8.4.7–8.4.9: người gán tự kiểm, người kiểm soát lô, lô lỗi được trả về sửa, và bản gốc lẫn bản sửa đều được giữ kèm thời điểm và người sửa. Vì vậy lần nộp lại có manifest mới với `revision` tăng lên và mã `sha256` của từng file, còn manifest lần trước được giữ lại.

**Mức lỗi và ngưỡng.** Ba mức nặng / chính / nhẹ và ngưỡng 5 % lỗi chính là luật của Phiếu QC 1 trong khóa này, không phải chuẩn ngành. Các ngày lab khác dùng thang và ngưỡng khác (Ngày 9 dùng mã E/W). ISO/IEC 5259-4 cũng không đặt ngưỡng lỗi: con số 5–10 % trong mục 8.4.8 là tỉ lệ lấy mẫu để kiểm cho việc nội bộ rủi ro thấp, không phải ngưỡng đạt. Khóa học dựng thang từ cách chia lớp lỗi của ISO 2859-1, xem [thang mức lỗi](qc_severity_road_v1.0.md).

**Đo chất lượng nhãn.** ISO/IEC 5259-2 đặt tên cho các phép đo mà road_check tính gần đúng: độ chính xác nhãn (Acc-ML-7, tỉ lệ nhãn đúng), độ đầy đủ nhãn (Com-ML-5, tỉ lệ mẫu không thiếu nhãn), độ nhất quán nhãn (Con-ML-2, hai người gán cùng mục có cùng nhãn không). Tên gọi chỉ để bạn đọc tài liệu ngành; điểm của lab vẫn tính theo rubric.

---
AI20K · AI in Action · VinUni. Dữ liệu BDD100K © 2018 The Regents of the University of California, theo BDD100K License.
