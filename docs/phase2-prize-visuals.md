# 로딩 마지막 경품 장면

## Latest revision: v2

- Current asset: `public/assets/prizes/prize-lineup-cutout-v2.png`, transparent RGBA, 1254 × 1254. Includes all six physical products in one composition. The loading screen no longer uses amount cards or a separate headphone layer.
- Generated with built-in image_gen using the v1 collage and Sony source image. Previous assets are retained as source history.
- Antigravity icon: `public/assets/logos/antigravity-icon-full-color.png`, downloaded from the [official press assets](https://antigravity.google/press), [full-color original](https://antigravity.google/assets/image/brand/antigravity-icon__full-color.png).

Final image edit prompt:

> Edit/composite these two input images into one NEW tightly art-directed product prize arrangement on genuine transparent alpha. Image 1 contains actual Samsung monitor/mobile stand, blue Orthomol Immun seven-day box/vial, Ghana chocolate, Snickers and Chupa Chups; image 2 the actual off-white Sony ULT WEAR headphones. Preserve all these exact six products, their branding, color, labels, and physical proportions. Reposition to make a lush coherent compact triangular product photo cluster filling a roughly square canvas, with very little empty space within the silhouette. Monitor and stand anchor center back; LARGE Sony headphones foreground left overlapping the lower left of monitor stand, Orthomol box/vial foreground right, Ghana angled slightly across lower middle, Snickers front left, lollipop front right with full stick visible. Product overlap should look intentional and balanced; snacks must be visible, not hidden. Use relative scale suitable for promotional composition, do not change shape of objects. No gift cards, no amount cards, no floating text, no prices, no currency, no fake coupons, no extra products, no gift boxes, no podium or floor, no background gradient, no confetti. Transparent background between and around the objects. Only faint natural contact shadows. Cutout silhouette, clean ecommerce product photography. Remove excess surrounding empty canvas: 3 percent safe margin at each edge, all products entirely in frame. Output transparent PNG.

## 사용자 제공 경품 목록

삼텐바이미 1개, 소니 ULT WEAR 2개, 오쏘몰 이뮨 7일분 2개, 네이버페이 5만원권 3개, 무신사 5만원권 3개, 배민 2만원권 5개, 스타벅스 1만원권 10개, 편의점 5천원권 24개, 가나초콜릿 10개, 스니커즈 10개, 츄파춥스 10개. 사용자가 제공한 표를 시각 구성에만 사용했다. DB 경품·재고·당첨확률과 운영 활성화 설정은 변경하지 않았다.

## 저장 자산과 처리

- `public/assets/prizes/prize-lineup-cutout-v1.png`: built-in imagegen으로 5개 제품 사진의 배경을 제거·합성한 RGBA PNG. 1536×1024, 완전 투명 픽셀 약 51%.
- `public/assets/prizes/sony-ult-wear.png`: Sony 제공 투명 PNG 원본. 제품 합성 옆에 별도 레이어로 표시한다.
- 상품권 5종은 브랜드명·금액을 HTML/CSS로 표시한 경품 안내 카드다. 실제 발급 쿠폰·바코드를 재현하지 않는다.
- 삼텐바이미 세부 모델·색상은 사용자 표에 없으므로 삼성 M5 화이트 이동식 스탠드 제품 사진을 대표 이미지로 사용했다. 오쏘몰·간식은 제품 포장 이미지를 사용한다. 운영 상품 확정 시 모델·용량·색상 일치를 확인한다.
- 5초 중 게임 → 주머니 → 긁기 → 경품 장면으로 이어진다. 제품·헤드셋·상품권을 시간차로 표시한다. 모션 감소에서는 정적으로 표시한다.
- 로컬의 마지막 장면 한 컷으로 투명 배경·배치를 확인했다. 전체 기능 테스트·부하 테스트·원격 배포는 사용자 요청대로 보류한다.

## 이미지 출처

배포 최적화(2026-09-26): 최종 v2 PNG를 동일 1254×1254 투명 WebP로 인코딩했다. PNG 1,960,753바이트 → WebP 341,606바이트. 실제 로딩은 `prize-lineup-cutout-v2.webp`를 사용하며 PNG는 편집 원본으로 보존한다.

- [삼성 M5 이동식 스탠드 — 하이마트](https://www.e-himart.co.kr/app/goods/goodsDetail?goodsNo=0021564793)
- [Sony ULT WEAR 공식 제품 사진](https://sony.scene7.com/is/image/sonyglobalsolutions/WH-ULT900N_Primary_image_Offwhite-1?fmt=png-alpha&hei=515&trf=trim&wid=515)
- [오쏘몰 이뮨 7일분 — JOYANCE-M](https://item.rakuten.co.jp/joyance-m/10000283/)
- [가나 밀크 — 메가마트](https://www.megamart.com/product/10433683)
- [스니커즈 — Redstone Foods](https://redstonefoods.com/products/256479--snickers-candy-bar-singles)
- [츄파춥스 — Coles](https://www.coles.com.au/product/chupa-chups-lollipop-12g-6043447)

## 최종 이미지 편집 프롬프트

도구: built-in `image_gen.imagegen`, CLI/API fallback 미사용. 입력 순서: 모니터·오쏘몰·가나·스니커즈·츄파춥스. 원본은 `.local/phase2/prize-sources/`에 보관한다.

> Use case: compositing + background-extraction. Create ONE photorealistic prize product collage with genuine transparent alpha background for a Korean mobile event loading animation. All five supplied images are EDIT TARGET products: (1) Samsung white monitor with its tall white round-base mobile stand, (2) Orthomol Immun seven-day blue box and vial, (3) red Lotte Ghana chocolate bar, (4) brown Snickers single bar, (5) wrapped Chupa Chups strawberry lollipop. Extract only the products, removing room scenery, white backgrounds, retailer headings/badges and inset detail circles. Preserve product silhouettes, materials, package branding, letters and proportions; do not redesign. Landscape 3:2 canvas, compact rich gift arrangement: tall monitor on stand dominant at center back, Orthomol box and vial lower right, Ghana/Snickers/Chupa Chups small fan across front. Leave left-middle area relatively free, since Sony headphones will be overlaid there separately in the webpage. Every product recognizable, light natural overlap, all edges intact, nothing cropped. No extra gift boxes, no podium, no environment, no confetti, no price text, no new typography/captions, no watermark. Products almost fill canvas with 4% safe margin. Subtle isolated contact shadows only; transparency around and between products. Accurate source products as clean premium ecommerce photo cutouts, not illustrations. Output transparent PNG.
