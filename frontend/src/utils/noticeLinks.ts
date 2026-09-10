// 나라장터 사전규격정보서비스(2026-09-05, 의사결정_로그 참고)는 API 응답에 상세 웹페이지
// URL이 없어, 한동안은 로그인 없이 받아지는 첨부파일 다운로드 URL을 notice.url 대신 썼다 —
// 그 결과 이 공고들은 "원문보기"를 눌러도 사이트가 아니라 파일이 열렸다. 2026-09-10 사용자가
// 직접 브라우저에서 실제 상세페이지 URL 패턴(`g2b.go.kr/link/PRVA004_02/?bfSpecRegNo=사전규격등록번호`,
// 로그인 불필요)을 확인해줘서 이제 신규 수집분은 이 진짜 링크를 쓴다(source_config v3,
// 의사결정_로그 참고). 이 함수는 그 전에 수집돼 아직 첨부파일 URL이 저장된 과거 공고를 위한
// 안전망으로 남긴다 — 새 URL은 두 패턴에 안 걸려 자동으로 "원문보기"로 정상 표시된다.
export function isAttachmentDownloadUrl(url: string): boolean {
  return /downloadFile\.do|UntyAtchFile/i.test(url);
}
