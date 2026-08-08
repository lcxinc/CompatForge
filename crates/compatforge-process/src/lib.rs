//! Cross-platform process supervision for authorized CompatForge launch plans.

#![forbid(unsafe_code)]

use compatforge_domain::{
    ContractError, LaunchPlan, OutputStream, ProcessExit, ProcessOutput, RuntimeEvent, RuntimeEventKind,
    SCHEMA_VERSION_V1,
};
use std::fmt;
use std::io::{self, BufRead, BufReader, Read};
use std::process::{Child, Command, ExitStatus, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError, Sender};
use std::sync::{Arc, Mutex, MutexGuard};
use std::thread;
use std::time::{Duration, Instant};

const PROCESS_POLL_INTERVAL: Duration = Duration::from_millis(20);

#[derive(Debug)]
pub enum ProcessError {
    InvalidPlan(ContractError),
    Spawn(io::Error),
    Terminate(io::Error),
}

impl fmt::Display for ProcessError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidPlan(error) => write!(formatter, "invalid launch plan: {error}"),
            Self::Spawn(error) => write!(formatter, "process spawn failed: {error}"),
            Self::Terminate(error) => write!(formatter, "process termination failed: {error}"),
        }
    }
}

impl std::error::Error for ProcessError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::InvalidPlan(error) => Some(error),
            Self::Spawn(error) | Self::Terminate(error) => Some(error),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum EventPoll {
    Event(RuntimeEvent),
    Timeout,
    Closed,
}

pub struct ProcessSupervisor;

impl ProcessSupervisor {
    /// Start a plan that has already been authorized against a trusted context.
    pub fn start(plan: &LaunchPlan) -> Result<LaunchHandle, ProcessError> {
        plan.validate().map_err(ProcessError::InvalidPlan)?;

        let mut command = Command::new(&plan.process.executable);
        command
            .args(&plan.process.arguments)
            .current_dir(&plan.process.working_directory)
            .env_clear()
            .envs(&plan.process.environment)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        let mut child = command.spawn().map_err(ProcessError::Spawn)?;
        let process_id = child.id();
        let stdout = child.stdout.take();
        let stderr = child.stderr.take();
        let child = Arc::new(Mutex::new(child));
        let finished = Arc::new(AtomicBool::new(false));
        let (sender, receiver) = mpsc::channel();
        let emitter = Arc::new(EventEmitter::new(plan.request_id.clone(), sender));
        emitter.emit(RuntimeEventKind::Started, Some(process_id), None, None, None);

        if let Some(pipe) = stdout {
            spawn_output_reader(pipe, OutputStream::Stdout, Arc::clone(&emitter));
        }
        if let Some(pipe) = stderr {
            spawn_output_reader(pipe, OutputStream::Stderr, Arc::clone(&emitter));
        }
        spawn_exit_watcher(Arc::clone(&child), Arc::clone(&finished), Arc::clone(&emitter));

        Ok(LaunchHandle {
            child,
            receiver: Mutex::new(receiver),
            emitter,
            finished,
        })
    }
}

pub struct LaunchHandle {
    child: Arc<Mutex<Child>>,
    receiver: Mutex<Receiver<RuntimeEvent>>,
    emitter: Arc<EventEmitter>,
    finished: Arc<AtomicBool>,
}

impl LaunchHandle {
    #[must_use]
    pub fn next_event(&self, timeout: Duration) -> EventPoll {
        let receiver = lock_recover(&self.receiver);
        match receiver.recv_timeout(timeout) {
            Ok(event) => EventPoll::Event(event),
            Err(RecvTimeoutError::Timeout) => EventPoll::Timeout,
            Err(RecvTimeoutError::Disconnected) => EventPoll::Closed,
        }
    }

    pub fn terminate(&self) -> Result<(), ProcessError> {
        if self.finished.load(Ordering::Acquire) {
            return Ok(());
        }

        let mut child = lock_recover(&self.child);
        if child.try_wait().map_err(ProcessError::Terminate)?.is_some() {
            self.finished.store(true, Ordering::Release);
            return Ok(());
        }
        self.emitter
            .emit(RuntimeEventKind::TerminateRequested, Some(child.id()), None, None, None);
        child.kill().map_err(ProcessError::Terminate)
    }

    #[must_use]
    pub fn is_finished(&self) -> bool {
        self.finished.load(Ordering::Acquire)
    }
}

impl Drop for LaunchHandle {
    fn drop(&mut self) {
        let _ = self.terminate();
    }
}

struct EventEmitter {
    request_id: String,
    started: Instant,
    state: Mutex<EventState>,
    sender: Sender<RuntimeEvent>,
}

struct EventState {
    sequence: u64,
    terminal: bool,
}

impl EventEmitter {
    fn new(request_id: String, sender: Sender<RuntimeEvent>) -> Self {
        Self {
            request_id,
            started: Instant::now(),
            state: Mutex::new(EventState {
                sequence: 0,
                terminal: false,
            }),
            sender,
        }
    }

    fn emit(
        &self,
        kind: RuntimeEventKind,
        process_id: Option<u32>,
        output: Option<ProcessOutput>,
        exit: Option<ProcessExit>,
        message: Option<String>,
    ) {
        let mut state = lock_recover(&self.state);
        if state.terminal {
            return;
        }
        let elapsed_milliseconds = u64::try_from(self.started.elapsed().as_millis()).unwrap_or(u64::MAX);
        let event = RuntimeEvent {
            schema_version: SCHEMA_VERSION_V1.into(),
            request_id: self.request_id.clone(),
            sequence: state.sequence,
            elapsed_milliseconds,
            kind,
            process_id,
            output,
            exit,
            message,
        };
        state.sequence = state.sequence.saturating_add(1);
        if kind == RuntimeEventKind::Exited {
            state.terminal = true;
        }
        let _ = self.sender.send(event);
    }
}

fn spawn_output_reader(pipe: impl Read + Send + 'static, stream: OutputStream, emitter: Arc<EventEmitter>) {
    let _ = thread::spawn(move || {
        let mut reader = BufReader::new(pipe);
        let mut buffer = Vec::new();
        loop {
            buffer.clear();
            match reader.read_until(b'\n', &mut buffer) {
                Ok(0) => break,
                Ok(_) => emitter.emit(
                    RuntimeEventKind::Output,
                    None,
                    Some(ProcessOutput {
                        stream,
                        text: String::from_utf8_lossy(&buffer).into_owned(),
                    }),
                    None,
                    None,
                ),
                Err(error) => {
                    emitter.emit(
                        RuntimeEventKind::Failed,
                        None,
                        None,
                        None,
                        Some(format!("failed to read {stream:?}: {error}")),
                    );
                    break;
                }
            }
        }
    });
}

fn spawn_exit_watcher(child: Arc<Mutex<Child>>, finished: Arc<AtomicBool>, emitter: Arc<EventEmitter>) {
    thread::spawn(move || {
        let result = loop {
            let result = lock_recover(&child).try_wait();
            match result {
                Ok(Some(status)) => break Ok(status),
                Ok(None) => thread::sleep(PROCESS_POLL_INTERVAL),
                Err(error) => break Err(error),
            }
        };

        match result {
            Ok(status) => emit_exit(&emitter, status),
            Err(error) => emitter.emit(
                RuntimeEventKind::Failed,
                None,
                None,
                None,
                Some(format!("process wait failed: {error}")),
            ),
        }
        finished.store(true, Ordering::Release);
    });
}

fn emit_exit(emitter: &EventEmitter, status: ExitStatus) {
    emitter.emit(
        RuntimeEventKind::Exited,
        None,
        None,
        Some(ProcessExit {
            code: status.code(),
            success: status.success(),
        }),
        None,
    );
}

fn lock_recover<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex.lock().unwrap_or_else(std::sync::PoisonError::into_inner)
}

#[cfg(test)]
mod tests {
    use super::*;
    use compatforge_domain::{
        GraphicsBackendKind, GraphicsSelection, NativeCommand, NetworkPolicy, RuntimeKind, RuntimeSelection,
        SandboxPolicy, SandboxProfile, TranslatorKind, TranslatorSelection,
    };
    use std::collections::BTreeMap;

    fn fixture_plan() -> LaunchPlan {
        LaunchPlan {
            schema_version: SCHEMA_VERSION_V1.into(),
            request_id: "process-test".into(),
            runtime: RuntimeSelection {
                provider: RuntimeKind::Wine,
                pack_id: "test-runtime".into(),
                pack_digest: format!("sha256:{}", "0".repeat(64)),
            },
            translator: TranslatorSelection {
                provider: TranslatorKind::Native,
                version: None,
            },
            graphics: GraphicsSelection {
                backend: GraphicsBackendKind::WineD3d,
                version: None,
                options: BTreeMap::new(),
            },
            process: NativeCommand {
                executable: std::env::current_exe().unwrap().to_string_lossy().into_owned(),
                arguments: vec!["--list".into()],
                environment: BTreeMap::new(),
                working_directory: std::env::current_dir().unwrap().to_string_lossy().into_owned(),
            },
            mounts: Vec::new(),
            sandbox: SandboxPolicy {
                profile: SandboxProfile::Desktop,
                network: NetworkPolicy::Deny,
                allow_devices: Vec::new(),
            },
            decision_trace: Vec::new(),
        }
    }

    #[test]
    fn emits_started_output_and_exit_in_sequence() {
        let handle = ProcessSupervisor::start(&fixture_plan()).unwrap();
        let deadline = Instant::now() + Duration::from_secs(10);
        let mut events = Vec::new();

        while Instant::now() < deadline {
            if let EventPoll::Event(event) = handle.next_event(Duration::from_millis(250)) {
                let exited = event.kind == RuntimeEventKind::Exited;
                events.push(event);
                if exited {
                    break;
                }
            }
        }

        assert_eq!(events.first().map(|event| event.kind), Some(RuntimeEventKind::Started));
        assert!(events.iter().any(|event| event.kind == RuntimeEventKind::Output));
        assert_eq!(events.last().map(|event| event.kind), Some(RuntimeEventKind::Exited));
        assert!(events.last().and_then(|event| event.exit.as_ref()).unwrap().success);
        assert!(events.windows(2).all(|pair| pair[0].sequence < pair[1].sequence));
    }

    #[test]
    fn runtime_events_round_trip_as_versioned_json() {
        let event = RuntimeEvent {
            schema_version: SCHEMA_VERSION_V1.into(),
            request_id: "round-trip".into(),
            sequence: 0,
            elapsed_milliseconds: 1,
            kind: RuntimeEventKind::Output,
            process_id: None,
            output: Some(ProcessOutput {
                stream: OutputStream::Stdout,
                text: "ready\n".into(),
            }),
            exit: None,
            message: None,
        };
        let json = serde_json::to_string(&event).unwrap();
        let restored: RuntimeEvent = serde_json::from_str(&json).unwrap();
        assert_eq!(restored, event);
    }
}
