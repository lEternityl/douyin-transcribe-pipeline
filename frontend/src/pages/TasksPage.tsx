import { useEffect, useState } from "react";
import { App as AntdApp, Button, Card, Popconfirm, Progress, Space, Table, Tag, Typography } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { DownloadTaskOut } from "../api/types";
import { useTaskProgress } from "../hooks/useTaskProgress";

const { Text } = Typography;

const statusColor: Record<string, string> = {
  pending: "default",
  running: "processing",
  done: "green",
  failed: "red",
  cancelled: "orange",
};

function RunningTask({ task, onCancel }: { task: DownloadTaskOut; onCancel: (id: number) => void }) {
  const { progress, finished } = useTaskProgress(task.id);
  const p = progress ?? {
    progress: task.progress,
    current: task.success_count + task.failed_count + task.skipped_count,
    total: task.total_videos,
    current_desc: "",
    success: task.success_count,
    failed: task.failed_count,
    skipped: task.skipped_count,
    status: task.status,
  };
  return (
    <Card size="small" style={{ marginBottom: 12 }}>
      <Space direction="vertical" style={{ width: "100%" }}>
        <Space>
          <Tag color={statusColor[p.status] || "default"}>{p.status}</Tag>
          <Text>任务 #{task.id}</Text>
          <Text type="secondary">用户ID: {task.user_id}</Text>
          <Text type="secondary">
            {p.current}/{p.total} (✓{p.success} ✗{p.failed} ⏭{p.skipped})
          </Text>
          <Popconfirm
            title="确认取消该任务?"
            description="仅标记为已取消,worker 实际执行可能稍后停止"
            onConfirm={() => onCancel(task.id)}
            okText="取消任务"
            cancelText="不了"
          >
            <Button size="small" danger>取消</Button>
          </Popconfirm>
        </Space>
        <Progress percent={p.progress} status={finished ? "success" : "active"} />
        {p.current_desc && <Text type="secondary">当前: {p.current_desc}</Text>}
      </Space>
    </Card>
  );
}

export default function TasksPage() {
  const qc = useQueryClient();
  const { message } = AntdApp.useApp();
  const { data: tasks, refetch } = useQuery({
    queryKey: ["tasks"],
    queryFn: api.listTasks,
    refetchInterval: 3000,
  });
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 2000);
    return () => clearInterval(t);
  }, []);

  const cancelMutation = useMutation({
    mutationFn: (id: number) => api.cancelTask(id),
    onSuccess: () => {
      message.success("已取消");
      qc.invalidateQueries({ queryKey: ["tasks"] });
    },
    onError: (e: Error) => message.error(`取消失败: ${e.message}`),
  });
  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.deleteTask(id),
    onSuccess: () => {
      message.success("已删除");
      qc.invalidateQueries({ queryKey: ["tasks"] });
    },
    onError: (e: Error) => message.error(`删除失败: ${e.message}`),
  });

  const running = (tasks ?? []).filter(
    (t) => t.status === "running" || t.status === "pending"
  );
  const history = (tasks ?? []).filter(
    (t) => t.status !== "running" && t.status !== "pending"
  );

  const columns = [
    { title: "#", dataIndex: "id", width: 60 },
    { title: "用户ID", dataIndex: "user_id", width: 80 },
    {
      title: "状态",
      dataIndex: "status",
      render: (s: string) => <Tag color={statusColor[s]}>{s}</Tag>,
      width: 90,
    },
    {
      title: "结果",
      render: (_: unknown, r: DownloadTaskOut) => (
        <Text>
          ✓{r.success_count} ✗{r.failed_count} ⏭{r.skipped_count} / {r.total_videos}
        </Text>
      ),
    },
    { title: "错误", dataIndex: "error_msg", ellipsis: true },
    { title: "创建时间", dataIndex: "created_at", width: 180 },
    {
      title: "操作",
      width: 160,
      render: (_: unknown, r: DownloadTaskOut) => {
        const active = r.status === "running" || r.status === "pending";
        return (
          <Space size="small">
            {active && (
              <Popconfirm
                title="确认取消该任务?"
                description="仅标记为已取消,worker 实际执行可能稍后停止"
                onConfirm={() => cancelMutation.mutate(r.id)}
                okText="取消任务"
                cancelText="不了"
              >
                <Button size="small" danger loading={cancelMutation.isPending}>
                  取消
                </Button>
              </Popconfirm>
            )}
            {!active && (
              <Popconfirm
                title="确认删除该任务记录?"
                onConfirm={() => deleteMutation.mutate(r.id)}
                okText="删除"
                cancelText="不了"
              >
                <Button size="small" loading={deleteMutation.isPending}>
                  删除
                </Button>
              </Popconfirm>
            )}
          </Space>
        );
      },
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          任务
        </Typography.Title>
        <Button onClick={() => refetch()}>刷新</Button>
        <Text type="secondary">{now && "自动刷新中"}</Text>
      </Space>

      {running.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <Typography.Title level={5}>进行中</Typography.Title>
          {running.map((t) => (
            <RunningTask key={t.id} task={t} onCancel={(id) => cancelMutation.mutate(id)} />
          ))}
        </div>
      )}

      <Typography.Title level={5}>历史</Typography.Title>
      <Table
        rowKey="id"
        dataSource={history}
        columns={columns}
        size="small"
        pagination={{ pageSize: 20 }}
      />
    </div>
  );
}
