import AddIcon from "@mui/icons-material/AddOutlined";
import EditIcon from "@mui/icons-material/EditOutlined";
import RefreshIcon from "@mui/icons-material/RefreshOutlined";
import {
  Alert,
  Box,
  Button,
  Card,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { rescanKeywords } from "@/api/keywords";
import { createTopic, fetchTopics, updateTopic, type Topic } from "@/api/topics";
import { TopicEditDialog } from "@/components/TopicEditDialog";
import { TopicKeywordsSection } from "@/components/TopicKeywordsSection";
import { useToast } from "@/components/ToastProvider";
import { apiErrorMessage } from "@/utils/errors";

// "관심 주제 목록"(L2-b 대분류, 설계안 05절) 관리자 CRUD 화면(2026-09-01 요청).
// 하드 삭제는 없음 — keyword_rule·customer_interest·notice_score가 참조하므로
// active 토글(비활성화)만 제공한다(소스 레지스트리와 같은 원칙).
export function TopicsPage() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const { data, isLoading } = useQuery({ queryKey: ["admin-topics"], queryFn: fetchTopics });
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingTopic, setEditingTopic] = useState<Topic | null>(null);
  const [rescanDialogOpen, setRescanDialogOpen] = useState(false);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-topics"] });

  const rescanMutation = useMutation({ mutationFn: rescanKeywords });

  function openRescanDialog() {
    rescanMutation.reset();
    setRescanDialogOpen(true);
  }

  const createMutation = useMutation({
    mutationFn: createTopic,
    onSuccess: () => {
      invalidate();
      setDialogOpen(false);
      notify("success", "관심주제를 추가했습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "관심주제 추가에 실패했습니다.")),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Parameters<typeof updateTopic>[1] }) => updateTopic(id, payload),
    onSuccess: () => {
      invalidate();
      setDialogOpen(false);
      notify("success", "관심주제를 저장했습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "관심주제 저장에 실패했습니다.")),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) => updateTopic(id, { active }),
    onSuccess: invalidate,
    onError: (error) => notify("error", apiErrorMessage(error, "상태 변경에 실패했습니다.")),
  });

  function openCreate() {
    setEditingTopic(null);
    setDialogOpen(true);
  }

  function openEdit(topic: Topic) {
    setEditingTopic(topic);
    setDialogOpen(true);
  }

  function handleSubmit(payload: { name: string; description: string | null; sort_order: number }) {
    if (editingTopic) {
      updateMutation.mutate({ id: editingTopic.id, payload });
    } else {
      createMutation.mutate(payload);
    }
  }

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 3 }}>
        <Box>
          <Typography variant="h2" sx={{ mb: 0.5 }}>
            관심주제 분류
          </Typography>
          <Typography variant="body2" color="text.secondary">
            고객이 관심 분야로 선택하는 대분류입니다(설계안 L2-b). 정부 표준분류 대신 직접
            큐레이션한 목록 — 너무 러프하지도, 너무 상세하지도 않은 15~25개 규모를 기준으로 합니다.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" startIcon={<RefreshIcon />} onClick={openRescanDialog}>
            키워드 재스캔
          </Button>
          <Button variant="contained" startIcon={<AddIcon />} onClick={openCreate}>
            새 분류
          </Button>
        </Stack>
      </Stack>

      <Card sx={{ overflowX: "auto" }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>번호</TableCell>
              <TableCell>관심주제</TableCell>
              <TableCell>키워드</TableCell>
              <TableCell>상태</TableCell>
              <TableCell align="right">관리</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {!isLoading &&
              data?.map((topic) => (
                <TableRow key={topic.id} sx={{ opacity: topic.active ? 1 : 0.5 }}>
                  <TableCell className="tnum">{topic.sort_order}</TableCell>
                  <TableCell>{topic.name}</TableCell>
                  <TableCell>
                    <TopicKeywordsSection topicId={topic.id} />
                  </TableCell>
                  <TableCell>
                    <Stack direction="row" alignItems="center" spacing={0.5}>
                      <Switch
                        size="small"
                        checked={topic.active}
                        onChange={(e) => toggleMutation.mutate({ id: topic.id, active: e.target.checked })}
                      />
                      <Chip label={topic.active ? "활성" : "비활성"} size="small" color={topic.active ? "success" : "default"} />
                    </Stack>
                  </TableCell>
                  <TableCell align="right">
                    <IconButton size="small" onClick={() => openEdit(topic)}>
                      <EditIcon fontSize="small" />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </Card>

      <TopicEditDialog
        open={dialogOpen}
        topic={editingTopic}
        submitting={createMutation.isPending || updateMutation.isPending}
        onClose={() => setDialogOpen(false)}
        onSubmit={handleSubmit}
      />

      <Dialog open={rescanDialogOpen} onClose={() => setRescanDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>키워드 재스캔</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            새로 추가·수정한 키워드를 이미 수집된 공고에도 소급 적용합니다. 기존에 이미 붙어있는
            관심주제는 절대 건드리지 않고, 새로 통과하는 조합만 추가합니다(LLM 호출 없음).
          </Alert>
          {rescanMutation.isSuccess && (
            <Alert severity="success">
              공고 {rescanMutation.data.scanned}건을 확인해 {rescanMutation.data.added}건의 관심주제를 새로 붙였습니다.
            </Alert>
          )}
          {rescanMutation.isError && (
            <Alert severity="error">{apiErrorMessage(rescanMutation.error, "키워드 재스캔에 실패했습니다.")}</Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRescanDialogOpen(false)}>닫기</Button>
          <Button variant="contained" disabled={rescanMutation.isPending} onClick={() => rescanMutation.mutate()}>
            실행
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
