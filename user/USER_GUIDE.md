#pragma once

#include <string>
#include <unordered_map>
#include <functional>

namespace mrorchords {

class KeyboardShortcuts {
public:
    KeyboardShortcuts() {
        // Initialize default shortcuts
        m_shortcuts = {
            { "Ctrl+N", std::bind(&KeyboardShortcuts::NewProject, this) },
            { "Ctrl+O", std::bind(&KeyboardShortcuts::OpenProject, this) },
            { "Ctrl+S", std::bind(&KeyboardShortcuts::SaveProject, this) },
            { "Ctrl+Shift+E", std::bind(&KeyboardShortcuts::ExportProject, this) },
            { "Space", std::bind(&KeyboardShortcuts::PlayPause, this) },
            { "Ctrl+Z", std::bind(&KeyboardShortcuts::Undo, this) },
            { "Ctrl+Y", std::bind(&KeyboardShortcuts::Redo, this) },
            { "Ctrl+C", std::bind(&KeyboardShortcuts::Copy, this) },
            { "Ctrl+V", std::bind(&KeyboardShortcuts::Paste, this) },
            { "Delete", std::bind(&KeyboardShortcuts::DeleteSelected, this) },
            { "Ctrl+F", std::bind(&KeyboardShortcuts::Find, this) },
            { "F1", std::bind(&KeyboardShortcuts::OpenHelp, this) },
            { "F5", std::bind(&KeyboardShortcuts::Refresh, this) },
            { "Ctrl+Shift+S", std::bind(&KeyboardShortcuts::SaveProjectAs, this) },
            { "Ctrl+I", std::bind(&KeyboardShortcuts::ImportMedia, this) },
            { "Ctrl+M", std::bind(&KeyboardShortcuts::MuteSelected, this) },
            { "Ctrl+U", std::bind(&KeyboardShortcuts::UnmuteSelected, this) },
            { "Ctrl+R", std::bind(&KeyboardShortcuts::RenderPreview, this) },
            { "Ctrl+Alt+S", std::bind(&KeyboardShortcuts::SaveSnapshot, this) },
            { "Ctrl+Shift+Z", std::bind(&KeyboardShortcuts::RedoRedo, this) },
            { "Ctrl+Shift+C", std::bind(&KeyboardShortcuts::CopyWithEffects, this) },
            { "Ctrl+Shift+V", std::bind(&KeyboardShortcuts::PasteWithEffects, this) },
            { "Ctrl+Shift+F", std::bind(&KeyboardShortcuts::FindAndReplace, this) },
            { "F2", std::bind(&KeyboardShortcuts::RenameSelected, this) },
            { "F3", std::bind(&KeyboardShortcuts::FindNext, this) },
            { "F4", std::bind(&KeyboardShortcuts::FindPrevious, this) },
            { "Ctrl+Shift+I", std::bind(&KeyboardShortcuts::ImportProject, this) },
            { "Ctrl+Shift+O", std::bind(&KeyboardShortcuts::OpenRecentProject, this) },
            { "Ctrl+Shift+P", std::bind(&KeyboardShortcuts::ProjectSettings, this) },
            { "Ctrl+Shift+M", std::bind(&KeyboardShortcuts::MuteAll, this) },
            { "Ctrl+Shift+U", std::bind(&KeyboardShortcuts::UnmuteAll, this) },
            { "Ctrl+Shift+R", std::bind(&KeyboardShortcuts::RenderAll, this) },
            { "F6", std::bind(&KeyboardShortcuts::ToggleFullscreen, this) },
            { "F7", std::bind(&KeyboardShortcuts::TogglePreview, this) },
            { "F8", std::bind(&KeyboardShortcuts::ToggleTimeline, this) },
            { "F9", std::bind(&KeyboardShortcuts::ToggleEffectsPanel, this) },
            { "F10", std::bind(&KeyboardShortcuts::TogglePropertiesPanel, this) },
            { "F11", std::bind(&KeyboardShortcuts::ToggleAudioPanel, this) },
            { "F12", std::bind(&KeyboardShortcuts::ToggleConsolePanel, this) }
        };
    }

    void RegisterShortcut(const std::string& shortcut, const std::function<void()>& handler) {
        m_shortcuts[shortcut] = handler;
    }

    void HandleKeyPress(const std::string& key) {
        auto it = m_shortcuts.find(key);
        if (it != m_shortcuts.end()) {
            it->second();
        }
    }

private:
    std::unordered_map<std::string, std::function<void()>> m_shortcuts;

    void NewProject() {
        // Implementation for creating a new project
    }

    void OpenProject() {
        // Implementation for opening an existing project
    }

    void SaveProject() {
        // Implementation for saving the current project
    }

    void ExportProject() {
        // Implementation for exporting the project
    }

    void PlayPause() {
        // Implementation for toggling play/pause
    }

    void Undo() {
        // Implementation for undoing the last action
    }

    void Redo() {
        // Implementation for redoing the last undone action
    }

    void Copy() {
        // Implementation for copying selected items
    }

    void Paste() {
        // Implementation for pasting copied items
    }

    void DeleteSelected() {
        // Implementation for deleting selected items
    }

    void Find() {
        // Implementation for opening the find dialog
    }

    void OpenHelp() {
        // Implementation for opening the help documentation
    }

    void Refresh() {
        // Implementation for refreshing the current view
    }

    void SaveProjectAs() {
        // Implementation for saving the project with a new name
    }

    void ImportMedia() {
        // Implementation for importing media files
    }

    void MuteSelected() {
        // Implementation for muting selected audio clips
    }

    void UnmuteSelected() {
        // Implementation for unmuting selected audio clips
    }

    void RenderPreview() {
        // Implementation for rendering the preview
    }

    void SaveSnapshot() {
        // Implementation for saving a snapshot of the current project state
    }

    void RedoRedo() {
        // Implementation for redoing the last action again
    }

    void CopyWithEffects() {
        // Implementation for copying with effects applied
    }

    void PasteWithEffects() {
        // Implementation for pasting with effects applied
    }

    void FindAndReplace() {
        // Implementation for opening the find and replace dialog
    }

    void RenameSelected() {
        // Implementation for renaming the selected item
    }

    void FindNext() {
        // Implementation for finding the next occurrence
    }

    void FindPrevious() {
        // Implementation for finding the previous occurrence
    }

    void ImportProject() {
        // Implementation for importing a project file
    }

    void OpenRecentProject() {
        // Implementation for opening a recently used project
    }

    void ProjectSettings() {
        // Implementation for opening the project settings dialog
    }

    void MuteAll() {
        // Implementation for muting all audio clips
    }

    void UnmuteAll() {
        // Implementation for unmuting all audio clips
    }

    void RenderAll() {
        // Implementation for rendering the entire project
    }

    void ToggleFullscreen() {
        // Implementation for toggling fullscreen mode
    }

    void TogglePreview() {
        // Implementation for toggling the preview panel
    }

    void ToggleTimeline() {
        // Implementation for toggling the timeline panel
    }

    void ToggleEffectsPanel() {
        // Implementation for toggling the effects panel
    }

    void TogglePropertiesPanel() {
        // Implementation for toggling the properties panel
    }

    void ToggleAudioPanel() {
        // Implementation for toggling the audio panel
    }

    void ToggleConsolePanel() {
        // Implementation for toggling the console panel
    }
};