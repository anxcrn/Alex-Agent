const { contextBridge, ipcRenderer, webUtils } = require('electron')

contextBridge.exposeInMainWorld('alexDesktop', {
  getConnection: profile => ipcRenderer.invoke('alex:connection', profile),
  revalidateConnection: () => ipcRenderer.invoke('alex:connection:revalidate'),
  touchBackend: profile => ipcRenderer.invoke('alex:backend:touch', profile),
  getGatewayWsUrl: profile => ipcRenderer.invoke('alex:gateway:ws-url', profile),
  openSessionWindow: (sessionId, opts) => ipcRenderer.invoke('alex:window:openSession', sessionId, opts),
  openNewSessionWindow: () => ipcRenderer.invoke('alex:window:openNewSession'),
  petOverlay: {
    // Main renderer → main process: window lifecycle + drag. `request` is
    // `{ bounds, screen }`; resolves with the screen bounds it actually used.
    open: request => ipcRenderer.invoke('alex:pet-overlay:open', request),
    close: () => ipcRenderer.invoke('alex:pet-overlay:close'),
    setBounds: bounds => ipcRenderer.send('alex:pet-overlay:set-bounds', bounds),
    setIgnoreMouse: ignore => ipcRenderer.send('alex:pet-overlay:ignore-mouse', ignore),
    // Flip the overlay focusable (and focus it) while the composer needs keys.
    setFocusable: focusable => ipcRenderer.send('alex:pet-overlay:set-focusable', focusable),
    // Main renderer → overlay (forwarded by main): push the latest pet state.
    pushState: payload => ipcRenderer.send('alex:pet-overlay:state', payload),
    // Overlay → main renderer (forwarded by main): pop back in / composer submit.
    control: payload => ipcRenderer.send('alex:pet-overlay:control', payload),
    // Overlay subscribes to state pushes.
    onState: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('alex:pet-overlay:state', listener)
      return () => ipcRenderer.removeListener('alex:pet-overlay:state', listener)
    },
    // Main renderer subscribes to overlay control messages.
    onControl: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('alex:pet-overlay:control', listener)
      return () => ipcRenderer.removeListener('alex:pet-overlay:control', listener)
    }
  },
  getBootProgress: () => ipcRenderer.invoke('alex:boot-progress:get'),
  getConnectionConfig: profile => ipcRenderer.invoke('alex:connection-config:get', profile),
  saveConnectionConfig: payload => ipcRenderer.invoke('alex:connection-config:save', payload),
  applyConnectionConfig: payload => ipcRenderer.invoke('alex:connection-config:apply', payload),
  testConnectionConfig: payload => ipcRenderer.invoke('alex:connection-config:test', payload),
  probeConnectionConfig: remoteUrl => ipcRenderer.invoke('alex:connection-config:probe', remoteUrl),
  oauthLoginConnectionConfig: remoteUrl => ipcRenderer.invoke('alex:connection-config:oauth-login', remoteUrl),
  oauthLogoutConnectionConfig: remoteUrl => ipcRenderer.invoke('alex:connection-config:oauth-logout', remoteUrl),
  profile: {
    get: () => ipcRenderer.invoke('alex:profile:get'),
    set: name => ipcRenderer.invoke('alex:profile:set', name)
  },
  api: request => ipcRenderer.invoke('alex:api', request),
  notify: payload => ipcRenderer.invoke('alex:notify', payload),
  requestMicrophoneAccess: () => ipcRenderer.invoke('alex:requestMicrophoneAccess'),
  readFileDataUrl: filePath => ipcRenderer.invoke('alex:readFileDataUrl', filePath),
  readFileText: filePath => ipcRenderer.invoke('alex:readFileText', filePath),
  selectPaths: options => ipcRenderer.invoke('alex:selectPaths', options),
  writeClipboard: text => ipcRenderer.invoke('alex:writeClipboard', text),
  saveImageFromUrl: url => ipcRenderer.invoke('alex:saveImageFromUrl', url),
  saveImageBuffer: (data, ext) => ipcRenderer.invoke('alex:saveImageBuffer', { data, ext }),
  saveClipboardImage: () => ipcRenderer.invoke('alex:saveClipboardImage'),
  getPathForFile: file => {
    try {
      return webUtils.getPathForFile(file) || ''
    } catch {
      return ''
    }
  },
  normalizePreviewTarget: (target, baseDir) => ipcRenderer.invoke('alex:normalizePreviewTarget', target, baseDir),
  watchPreviewFile: url => ipcRenderer.invoke('alex:watchPreviewFile', url),
  stopPreviewFileWatch: id => ipcRenderer.invoke('alex:stopPreviewFileWatch', id),
  setTitleBarTheme: payload => ipcRenderer.send('alex:titlebar-theme', payload),
  setNativeTheme: mode => ipcRenderer.send('alex:native-theme', mode),
  setTranslucency: payload => ipcRenderer.send('alex:translucency', payload),
  setPreviewShortcutActive: active => ipcRenderer.send('alex:previewShortcutActive', Boolean(active)),
  openExternal: url => ipcRenderer.invoke('alex:openExternal', url),
  openPreviewInBrowser: url => ipcRenderer.invoke('alex:openPreviewInBrowser', url),
  fetchLinkTitle: url => ipcRenderer.invoke('alex:fetchLinkTitle', url),
  sanitizeWorkspaceCwd: cwd => ipcRenderer.invoke('alex:workspace:sanitize', cwd),
  settings: {
    getDefaultProjectDir: () => ipcRenderer.invoke('alex:setting:defaultProjectDir:get'),
    setDefaultProjectDir: dir => ipcRenderer.invoke('alex:setting:defaultProjectDir:set', dir),
    pickDefaultProjectDir: () => ipcRenderer.invoke('alex:setting:defaultProjectDir:pick')
  },
  revealLogs: () => ipcRenderer.invoke('alex:logs:reveal'),
  getRecentLogs: () => ipcRenderer.invoke('alex:logs:recent'),
  readDir: dirPath => ipcRenderer.invoke('alex:fs:readDir', dirPath),
  gitRoot: startPath => ipcRenderer.invoke('alex:fs:gitRoot', startPath),
  revealPath: targetPath => ipcRenderer.invoke('alex:fs:reveal', targetPath),
  renamePath: (targetPath, newName) => ipcRenderer.invoke('alex:fs:rename', targetPath, newName),
  writeTextFile: (filePath, content) => ipcRenderer.invoke('alex:fs:writeText', filePath, content),
  trashPath: targetPath => ipcRenderer.invoke('alex:fs:trash', targetPath),
  git: {
    worktreeList: repoPath => ipcRenderer.invoke('alex:git:worktreeList', repoPath),
    worktreeAdd: (repoPath, options) => ipcRenderer.invoke('alex:git:worktreeAdd', repoPath, options),
    worktreeRemove: (repoPath, worktreePath, options) =>
      ipcRenderer.invoke('alex:git:worktreeRemove', repoPath, worktreePath, options),
    branchSwitch: (repoPath, branch) => ipcRenderer.invoke('alex:git:branchSwitch', repoPath, branch),
    branchList: repoPath => ipcRenderer.invoke('alex:git:branchList', repoPath),
    repoStatus: repoPath => ipcRenderer.invoke('alex:git:repoStatus', repoPath),
    fileDiff: (repoPath, filePath) => ipcRenderer.invoke('alex:git:fileDiff', repoPath, filePath),
    scanRepos: (roots, options) => ipcRenderer.invoke('alex:git:scanRepos', roots, options),
    review: {
      list: (repoPath, scope, baseRef) => ipcRenderer.invoke('alex:git:review:list', repoPath, scope, baseRef),
      diff: (repoPath, filePath, scope, baseRef, staged) =>
        ipcRenderer.invoke('alex:git:review:diff', repoPath, filePath, scope, baseRef, staged),
      stage: (repoPath, filePath) => ipcRenderer.invoke('alex:git:review:stage', repoPath, filePath),
      unstage: (repoPath, filePath) => ipcRenderer.invoke('alex:git:review:unstage', repoPath, filePath),
      revert: (repoPath, filePath) => ipcRenderer.invoke('alex:git:review:revert', repoPath, filePath),
      revParse: (repoPath, ref) => ipcRenderer.invoke('alex:git:review:revParse', repoPath, ref),
      commit: (repoPath, message, push) => ipcRenderer.invoke('alex:git:review:commit', repoPath, message, push),
      commitContext: repoPath => ipcRenderer.invoke('alex:git:review:commitContext', repoPath),
      push: repoPath => ipcRenderer.invoke('alex:git:review:push', repoPath),
      shipInfo: repoPath => ipcRenderer.invoke('alex:git:review:shipInfo', repoPath),
      createPr: repoPath => ipcRenderer.invoke('alex:git:review:createPr', repoPath)
    }
  },
  terminal: {
    dispose: id => ipcRenderer.invoke('alex:terminal:dispose', id),
    resize: (id, size) => ipcRenderer.invoke('alex:terminal:resize', id, size),
    start: options => ipcRenderer.invoke('alex:terminal:start', options),
    write: (id, data) => ipcRenderer.invoke('alex:terminal:write', id, data),
    onData: (id, callback) => {
      const channel = `alex:terminal:${id}:data`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)
      return () => ipcRenderer.removeListener(channel, listener)
    },
    onExit: (id, callback) => {
      const channel = `alex:terminal:${id}:exit`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)
      return () => ipcRenderer.removeListener(channel, listener)
    }
  },
  onClosePreviewRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('alex:close-preview-requested', listener)
    return () => ipcRenderer.removeListener('alex:close-preview-requested', listener)
  },
  onOpenUpdatesRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('alex:open-updates', listener)
    return () => ipcRenderer.removeListener('alex:open-updates', listener)
  },
  onDeepLink: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('alex:deep-link', listener)
    return () => ipcRenderer.removeListener('alex:deep-link', listener)
  },
  signalDeepLinkReady: () => ipcRenderer.invoke('alex:deep-link-ready'),
  onWindowStateChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('alex:window-state-changed', listener)
    return () => ipcRenderer.removeListener('alex:window-state-changed', listener)
  },
  onFocusSession: callback => {
    const listener = (_event, sessionId) => callback(sessionId)
    ipcRenderer.on('alex:focus-session', listener)
    return () => ipcRenderer.removeListener('alex:focus-session', listener)
  },
  onNotificationAction: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('alex:notification-action', listener)
    return () => ipcRenderer.removeListener('alex:notification-action', listener)
  },
  onPreviewFileChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('alex:preview-file-changed', listener)
    return () => ipcRenderer.removeListener('alex:preview-file-changed', listener)
  },
  onBackendExit: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('alex:backend-exit', listener)
    return () => ipcRenderer.removeListener('alex:backend-exit', listener)
  },
  onPowerResume: callback => {
    const listener = () => callback()
    ipcRenderer.on('alex:power-resume', listener)
    return () => ipcRenderer.removeListener('alex:power-resume', listener)
  },
  onBootProgress: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('alex:boot-progress', listener)
    return () => ipcRenderer.removeListener('alex:boot-progress', listener)
  },
  // First-launch bootstrap progress -- emitted by the install.ps1 stage
  // runner in main.cjs (apps/desktop/electron/bootstrap-runner.cjs).
  // Renderer's install overlay subscribes to live events and queries the
  // current snapshot via getBootstrapState() to recover after a devtools
  // reload mid-bootstrap.
  getBootstrapState: () => ipcRenderer.invoke('alex:bootstrap:get'),
  resetBootstrap: () => ipcRenderer.invoke('alex:bootstrap:reset'),
  repairBootstrap: () => ipcRenderer.invoke('alex:bootstrap:repair'),
  cancelBootstrap: () => ipcRenderer.invoke('alex:bootstrap:cancel'),
  onBootstrapEvent: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('alex:bootstrap:event', listener)
    return () => ipcRenderer.removeListener('alex:bootstrap:event', listener)
  },
  getVersion: () => ipcRenderer.invoke('alex:version'),
  getRemoteDisplayReason: () => ipcRenderer.invoke('alex:get-remote-display-reason'),
  uninstall: {
    summary: () => ipcRenderer.invoke('alex:uninstall:summary'),
    run: mode => ipcRenderer.invoke('alex:uninstall:run', { mode })
  },
  updates: {
    check: () => ipcRenderer.invoke('alex:updates:check'),
    apply: opts => ipcRenderer.invoke('alex:updates:apply', opts),
    getBranch: () => ipcRenderer.invoke('alex:updates:branch:get'),
    setBranch: name => ipcRenderer.invoke('alex:updates:branch:set', name),
    onProgress: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('alex:updates:progress', listener)
      return () => ipcRenderer.removeListener('alex:updates:progress', listener)
    }
  },
  themes: {
    fetchMarketplace: id => ipcRenderer.invoke('alex:vscode-theme:fetch', id),
    searchMarketplace: query => ipcRenderer.invoke('alex:vscode-theme:search', query)
  }
})
