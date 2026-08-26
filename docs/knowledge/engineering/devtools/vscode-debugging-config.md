# VS Code Debugging Configuration

Debugging in Visual Studio Code is a powerful feature that helps developers identify and fix issues in their code efficiently. This article covers essential debugging configurations and techniques to enhance your development workflow.

## launch.json Configuration

The `launch.json` file defines debugging configurations for your project. It's located in the `.vscode` folder of your workspace.

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Launch Program",
      "type": "node",
      "request": "launch",
      "program": "${workspaceFolder}/app.js",
      "console": "integratedTerminal"
    }
  ]
}
```

## Attach to Process

Attach debugging to an already running process using the attach configuration:

```json
{
  "name": "Attach to Process",
  "type": "node",
  "request": "attach",
  "processId": "${command:PickProcess}"
}
```

## Remote Debugging

Remote debugging allows you to debug applications running on remote servers or containers:

```json
{
  "name": "Remote Debug",
  "type": "node",
  "request": "attach",
  "address": "localhost",
  "port": 9229,
  "localRoot": "${workspaceFolder}",
  "remoteRoot": "/app"
}
```

## Source Maps Support

VS Code automatically handles source maps for TypeScript and other compiled languages:

```json
{
  "name": "TypeScript Debug",
  "type": "node",
  "request": "launch",
  "program": "${workspaceFolder}/dist/app.js",
  "sourceMaps": true,
  "outFiles": ["${workspaceFolder}/dist/**/*.js"]
}
```

## Conditional Breakpoints

Set breakpoints that only trigger when specific conditions are met:

```javascript
// In your code, set condition like: i > 10
for (let i = 0; i < 20; i++) {
  console.log(i); // Breakpoint with condition: i > 10
}
```

## Logpoints

Use logpoints to output messages without stopping execution:

```javascript
// Set logpoint with message: "Processing item: ${item}"
function processData(item) {
  return item * 2;
}
```

## Advanced Configuration Example

Complete debugging setup for a Node.js application:

```
