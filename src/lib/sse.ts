export interface LogEvent {
  type?: string;
  stepIndex?: number;
  level?: "info" | "success" | "error";
  message?: string;
  ts?: number;
  status?: string;
  [key: string]: unknown;
}

type Subscriber = (event: LogEvent) => void;

interface Channel {
  subscribers: Set<Subscriber>;
  buffer: LogEvent[];
  closed: boolean;
}

class SSEChannelRegistry {
  private channels = new Map<string, Channel>();

  create(executionId: string) {
    this.channels.set(executionId, {
      subscribers: new Set(),
      buffer: [],
      closed: false,
    });
  }

  subscribe(executionId: string, cb: Subscriber): () => void {
    const channel = this.channels.get(executionId);
    if (!channel) return () => {};
    channel.buffer.forEach(cb);
    channel.subscribers.add(cb);
    return () => channel.subscribers.delete(cb);
  }

  push(executionId: string, event: LogEvent) {
    const channel = this.channels.get(executionId);
    if (!channel || channel.closed) return;
    channel.buffer.push(event);
    channel.subscribers.forEach((cb) => cb(event));
  }

  close(executionId: string) {
    const channel = this.channels.get(executionId);
    if (channel) {
      channel.closed = true;
      channel.subscribers.clear();
    }
  }

  remove(executionId: string) {
    this.channels.delete(executionId);
  }

  get(executionId: string) {
    const ch = this.channels.get(executionId);
    if (!ch) return null;
    return {
      push: (event: LogEvent) => this.push(executionId, event),
      close: () => this.close(executionId),
    };
  }
}

export const sseChannel = new SSEChannelRegistry();
