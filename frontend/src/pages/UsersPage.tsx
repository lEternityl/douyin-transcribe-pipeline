import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  App as AntdApp,
  Button,
  Card,
  Input,
  Modal,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { UserOut } from "../api/types";

const { Text } = Typography;

export default function UsersPage() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const { message } = AntdApp.useApp();
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [importOpen, setImportOpen] = useState(false);
  const [tableText, setTableText] = useState("");
  const [downloadOpen, setDownloadOpen] = useState(false);
  const [maxVideos, setMaxVideos] = useState(0);

  // URL 一键转写
  const [urlInput, setUrlInput] = useState("");
  const [urlMaxVideos, setUrlMaxVideos] = useState(0);
  const [urlDeleteMp3, setUrlDeleteMp3] = useState(true);

  const { data: users, isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: api.listUsers,
  });

  const parseMutation = useMutation({
    mutationFn: (content: string) => api.parseTable(content),
    onSuccess: (r) => {
      message.success(`导入完成: 新增 ${r.inserted}, 更新 ${r.updated}, 共 ${r.total}`);
      setImportOpen(false);
      setTableText("");
      qc.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (e: Error) => message.error(`导入失败: ${e.message}`),
  });

  const downloadMutation = useMutation({
    mutationFn: () => api.createDownload(selectedIds, maxVideos),
    onSuccess: (r) => {
      message.success(`已创建 ${r.length} 个下载任务`);
      setDownloadOpen(false);
      qc.invalidateQueries({ queryKey: ["tasks"] });
      nav("/tasks");
    },
    onError: (e: Error) => message.error(`创建任务失败: ${e.message}`),
  });

  const urlMutation = useMutation({
    mutationFn: () =>
      api.importUrl(urlInput, {
        maxVideosPerUser: urlMaxVideos,
        deleteMp3: urlDeleteMp3,
        autoStart: true,
      }),
    onSuccess: (r) => {
      message.success(`已创建用户并启动流水线任务 #${r.task_id}`);
      setUrlInput("");
      qc.invalidateQueries({ queryKey: ["users"] });
      nav("/tasks");
    },
    onError: (e: Error) => message.error(`启动失败: ${e.message}`),
  });

  const columns = [
    { title: "序号", dataIndex: "seq", width: 70 },
    { title: "昵称", dataIndex: "nickname" },
    { title: "抖音号", dataIndex: "douyin_id" },
    { title: "粉丝", dataIndex: "followers", width: 90 },
    {
      title: "下载",
      render: (_: unknown, r: UserOut) => (
        <Tag color={r.downloaded_count > 0 ? "green" : "default"}>
          {r.downloaded_count}/{r.video_count || "?"}
        </Tag>
      ),
      width: 90,
    },
    {
      title: "操作",
      render: (_: unknown, r: UserOut) => (
        <a onClick={() => nav(`/users/${r.id}`)}>详情</a>
      ),
      width: 80,
    },
  ];

  return (
    <div>
      {/* ===== URL 一键转写 ===== */}
      <Card title="一键转写" size="small" style={{ marginBottom: 16 }}>
        <Space.Compact style={{ width: "100%" }}>
          <Input
            placeholder="粘贴抖音用户主页 URL,如 https://www.douyin.com/user/MS4w..."
            value={urlInput}
            onChange={(e) => setUrlInput(e.target.value)}
            onPressEnter={() => urlInput && urlMutation.mutate()}
            size="large"
          />
          <Button
            type="primary"
            size="large"
            loading={urlMutation.isPending}
            disabled={!urlInput.trim()}
            onClick={() => urlMutation.mutate()}
          >
            开始转写
          </Button>
        </Space.Compact>
        <Space style={{ marginTop: 8 }}>
          <Text type="secondary">每用户最多:</Text>
          <Input
            style={{ width: 100 }}
            type="number"
            value={urlMaxVideos}
            onChange={(e) => setUrlMaxVideos(Number(e.target.value) || 0)}
            min={0}
            size="small"
          />
          <Text type="secondary">0=全部</Text>
          <Switch
            checkedChildren="转写后删MP3"
            unCheckedChildren="保留MP3"
            checked={urlDeleteMp3}
            onChange={setUrlDeleteMp3}
            size="small"
          />
        </Space>
      </Card>

      {/* ===== 用户列表 ===== */}
      <Space style={{ marginBottom: 16 }}>
        <Button onClick={() => setImportOpen(true)}>导入表格</Button>
        <Button
          disabled={selectedIds.length === 0}
          onClick={() => setDownloadOpen(true)}
        >
          批量下载 ({selectedIds.length})
        </Button>
      </Space>

      <Table
        rowKey="id"
        loading={isLoading}
        dataSource={users}
        columns={columns}
        size="small"
        rowSelection={{
          selectedRowKeys: selectedIds,
          onChange: (keys) => setSelectedIds(keys as number[]),
        }}
        onRow={(r) => ({ onDoubleClick: () => nav(`/users/${r.id}`) })}
        pagination={{ pageSize: 20 }}
      />

      <Modal
        title="导入 markdown 表格"
        open={importOpen}
        onCancel={() => setImportOpen(false)}
        confirmLoading={parseMutation.isPending}
        onOk={() => parseMutation.mutate(tableText)}
        okText="导入"
        width={720}
      >
        <Input.TextArea
          rows={14}
          value={tableText}
          onChange={(e) => setTableText(e.target.value)}
          placeholder="粘贴表格内容,如:&#10;| 序号 | 昵称 | 抖音号 | 获赞 | 粉丝 | 主页链接 |&#10;|---|---|---|---|---|---|&#10;| 1 | xxx | xxx | 1.0万 | 500 | https://www.douyin.com/user/... |"
        />
      </Modal>

      <Modal
        title="批量下载"
        open={downloadOpen}
        onCancel={() => setDownloadOpen(false)}
        confirmLoading={downloadMutation.isPending}
        onOk={() => downloadMutation.mutate()}
        okText="开始下载"
      >
        <p>将为 {selectedIds.length} 个用户创建下载任务。</p>
        <Space>
          <span>每用户最多下载数(0=全部):</span>
          <Input
            style={{ width: 120 }}
            type="number"
            value={maxVideos}
            onChange={(e) => setMaxVideos(Number(e.target.value) || 0)}
            min={0}
          />
        </Space>
      </Modal>
    </div>
  );
}
