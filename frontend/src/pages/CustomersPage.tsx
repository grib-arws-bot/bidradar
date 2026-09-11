import AddIcon from "@mui/icons-material/AddOutlined";
import ChevronRightIcon from "@mui/icons-material/ChevronRightOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import {
  Box,
  Button,
  Card,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  MenuItem,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { createCustomer, deleteCustomer, fetchCustomersFull, type CustomerDraft } from "@/api/customers";
import { useToast } from "@/components/ToastProvider";
import { apiErrorMessage } from "@/utils/errors";

const EMPTY_DRAFT: CustomerDraft = {
  name: "",
  plan_tier: "standard",
  contact_email: "",
  contact_name: "",
  contact_title: "",
  contact_phone: "",
  report_recipient_emails: [],
  reference_urls: [],
  active: true,
};

// 고객 목록(2026-09-05 신설 → 09-05 상세페이지 분리) — 담당자·소개서·관심주제·리포트 등
// 고객 하나의 상세 정보는 전부 CustomerDetailPage(행 클릭 시 이동)에서 다룬다. 이 페이지는
// 목록 조회·신규 생성·삭제만.
export function CustomersPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const customersQuery = useQuery({ queryKey: ["customers-full"], queryFn: fetchCustomersFull });

  const [dialogOpen, setDialogOpen] = useState(false);
  const [draft, setDraft] = useState<CustomerDraft>(EMPTY_DRAFT);

  function invalidateCustomers() {
    queryClient.invalidateQueries({ queryKey: ["customers-full"] });
    queryClient.invalidateQueries({ queryKey: ["customers"] }); // 고객 선택 드롭다운(보고서 관리 등)도 갱신
  }

  const createMutation = useMutation({
    mutationFn: (d: CustomerDraft) => createCustomer(d),
    onSuccess: ({ id }) => {
      invalidateCustomers();
      setDialogOpen(false);
      notify("success", "고객을 등록했습니다.");
      navigate(`/customers/${id}`);
    },
    onError: (error) => notify("error", apiErrorMessage(error, "고객 등록에 실패했습니다.")),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteCustomer(id),
    onSuccess: () => {
      invalidateCustomers();
      notify("success", "고객을 삭제했습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "고객 삭제에 실패했습니다.")),
  });

  function openCreate() {
    setDraft(EMPTY_DRAFT);
    setDialogOpen(true);
  }

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.5 }}>
        <Typography variant="h2">고객 관리</Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={openCreate}>
          신규 고객
        </Button>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        고객을 선택하면 담당자·소개서 파일·관심주제 등 상세 정보를 볼 수 있습니다.
      </Typography>

      <Card sx={{ overflowX: "auto" }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>고객명</TableCell>
              <TableCell>등급</TableCell>
              <TableCell>담당자</TableCell>
              <TableCell>연락처</TableCell>
              <TableCell>이메일</TableCell>
              <TableCell align="right">활성</TableCell>
              <TableCell align="right">관리</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(customersQuery.data ?? []).map((c) => (
              <TableRow key={c.id} hover sx={{ cursor: "pointer" }} onClick={() => navigate(`/customers/${c.id}`)}>
                <TableCell>{c.name}</TableCell>
                <TableCell>{c.plan_tier === "internal" ? "그립 자신" : c.plan_tier}</TableCell>
                <TableCell>
                  {[c.contact_name, c.contact_title].filter(Boolean).join(" / ") || "—"}
                </TableCell>
                <TableCell>{c.contact_phone || "—"}</TableCell>
                <TableCell>{c.contact_email || "—"}</TableCell>
                <TableCell align="right">
                  <Chip size="small" label={c.active ? "활성" : "비활성"} color={c.active ? "success" : "default"} />
                </TableCell>
                <TableCell align="right" onClick={(e) => e.stopPropagation()}>
                  {c.plan_tier !== "internal" && (
                    <Tooltip title="삭제">
                      <IconButton size="small" color="error" onClick={() => deleteMutation.mutate(c.id)}>
                        <DeleteOutlineIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  )}
                  <IconButton size="small" onClick={() => navigate(`/customers/${c.id}`)}>
                    <ChevronRightIcon fontSize="small" />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>신규 고객</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="고객명"
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              autoFocus
              required
            />
            <TextField
              select
              label="등급"
              value={draft.plan_tier}
              onChange={(e) => setDraft({ ...draft, plan_tier: e.target.value as CustomerDraft["plan_tier"] })}
            >
              <MenuItem value="standard">standard</MenuItem>
              <MenuItem value="premium">premium</MenuItem>
            </TextField>

            <Stack direction="row" spacing={1.5}>
              <TextField
                size="small"
                label="담당자 이름"
                value={draft.contact_name ?? ""}
                onChange={(e) => setDraft({ ...draft, contact_name: e.target.value })}
                fullWidth
              />
              <TextField
                size="small"
                label="이메일"
                value={draft.contact_email ?? ""}
                onChange={(e) => setDraft({ ...draft, contact_email: e.target.value })}
                fullWidth
              />
            </Stack>

            <FormControlLabel
              control={
                <Switch checked={draft.active} onChange={(e) => setDraft({ ...draft, active: e.target.checked })} />
              }
              label="활성"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>취소</Button>
          <Button
            variant="contained"
            disabled={!draft.name.trim() || createMutation.isPending}
            onClick={() => createMutation.mutate(draft)}
          >
            생성 후 상세 이동
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
