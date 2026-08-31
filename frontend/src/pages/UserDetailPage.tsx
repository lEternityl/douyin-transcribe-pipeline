import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  App as AntdApp,
  Button,
  Modal,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  Input,
  Empty,
  Collapse,
} from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { FileOut, TranscriptionOut } from "../api/types";

const { Text, Paragraph } = Typography;

export default function UserDetailPage() {
  const { id } = useParams<{ id: string }>();
  const userId = Number(id);
  const nav = useNavigate();
  const qc = useQueryClient();
  const { message } = AntdApp.useApp();

  const [pipelineOpen, setPipelineOpen] = useState(false);
  const [pipeMaxVideos, setPipeMaxVideos] = useState(0);
  const [pipeDeleteMp3, setPipeDeleteMp3] = useState(true);

  const { data: user } = useQuery({
    queryKey: ["user", userId],
    queryFn: () => api.getUser(userId),
    enabled: !!userId,
  });
  const { data: files } = useQuery({
    queryKey: ["files", userId],
    queryFn: () => api.listFiles(userId),
    enabled: !!userId,
  });
  const { data: transcriptions } = useQuery({
    queryKey: ["transcriptions", userId],
    queryFn: () => api.listTranscriptions(userId),
    enabled: !!userId,
  });
  const { data: merged } = useQuery({
    queryKey: ["merged-text", userId],
    queryFn: () => api.getMergedText(userId),
    enabled: !!userId,
  });

  const deleteMutation = useMutation({
    mutationFn: (videoId: number) => api.deleteFile(videoId),
    onSuccess: () => {
      message.success("已删除");
      qc.invalidateQueries({ queryKey: ["files", userId] });
      qc.invalidateQueries({ queryKey: ["user", userId] });
    },
    onError: (e: Error) => message.error(`删除失败: ${e.message}`),
  });

  const pipelineMutation = useMutation({
    mutationFn: () => api.createPipeline(userId, pipeMaxVideos, pipeDeleteMp3),
    onSuccess: (r) => {
      message.success(`流水线任务已创建 #${r.task_id}`);
      setPipelineOpen(false);
      nav("/tasks");
    },
    onError: (e: Error) => message.error(`创建失败: ${e.message}`),
  });

  const fileColumns = [
    { title: "文件名", dataIndex: "filename" },
    { title: "大小(KB)", dataIndex: "size_kb", width: 100 },
    {
      title: "操作",
      width: 280,
      render: (_: unknown, r: FileOut) => (
        <Space>
          <audio controls preload="none" src={api.fileUrl(r.video_id)} style={{ height: 28 }} />
          <Button size="small" href={api.fileUrl(r.video_id)} download>
            下载
          </Button>
          <Button
            size="small"
            danger
            loading={deleteMutation.isPending}
            onClick={() => deleteMutation.mutate(r.video_id)}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          {user?.nickname}
        </Typography.Title>
        <Text type="secondary">抖音号: {user?.douyin_id || "-"}</Text>
        <Tag color={user && user.downloaded_count > 0 ? "green" : "default"}>
          已下载 {user?.downloaded_count ?? 0}/{user?.video_count ?? 0}
        </Tag>
        <Button type="primary" onClick={() => setPipelineOpen(true)}>
          一键转写
        </Button>
      </Space>

      <Tabs
        items={[
          {
            key: "files",
            label: `音频文件 (${files?.length ?? 0})`,
            children: (
              <Table
                rowKey="video_id"
                dataSource={files}
                columns={fileColumns}
                size="small"
                pagination={{ pageSize: 50 }}
                locale={{ emptyText: <Empty description="暂无音频文件(可能已被转写后清理)" /> }}
              />
            ),
          },
          {
            key: "transcriptions",
            label: `转写文本 (${transcriptions?.length ?? 0})`,
            children: (
              <div>
                {transcriptions && transcriptions.length > 0 ? (
                  <Collapse
                    items={transcriptions.map((t: TranscriptionOut) => ({
                      key: t.id,
                      label: (
                        <Space>
                          <Tag color={t.status === "done" ? "green" : t.status === "failed" ? "red" : "blue"}>
                            {t.status}
                          </Tag>
                          <Text>{t.desc || `视频 ${t.video_id}`}</Text>
                        </Space>
                      ),
                      children: t.status === "done" ? (
                        <Paragraph style={{ whiteSpace: "pre-wrap" }}>{t.text}</Paragraph>
                      ) : (
                        <Text type="danger">转写失败: {t.error_msg}</Text>
                      ),
                    }))}
                  />
                ) : (
                  <Empty description="暂无转写文本,点击上方「一键转写」开始" />
                )}
              </div>
            ),
          },
          {
            key: "merged",
            label: "合并文本",
            children: (
              <div>
                {merged?.content ? (
                  <Input.TextArea
                    value={merged.content}
                    readOnly
                    autoSize={{ minRows: 20, maxRows: 40 }}
                    style={{ fontFamily: "monospace" }}
                  />
                ) : (
                  <Empty description="暂无合并文本" />
                )}
              </div>
            ),
          },
        ]}
      />

      <Modal
        title="一键转写流水线"
        open={pipelineOpen}
        onCancel={() => setPipelineOpen(false)}
        confirmLoading={pipelineMutation.isPending}
        onOk={() => pipelineMutation.mutate()}
        okText="开始"
      >
        <p>将执行: 下载音频 → 转写文字 → 合并文本 → 清理 MP3</p>
        <Space direction="vertical">
          <Space>
            <span>每用户最多下载数(0=全部):</span>
            <Input
              style={{ width: 120 }}
              type="number"
              value={pipeMaxVideos}
              onChange={(e) => setPipeMaxVideos(Number(e.target.value) || 0)}
              min={0}
            />
          </Space>
          <Switch
            checkedChildren="转写后删除 MP3"
            unCheckedChildren="保留 MP3"
            checked={pipeDeleteMp3}
            onChange={setPipeDeleteMp3}
          />
        </Space>
      </Modal>
    </div>
  );
}
