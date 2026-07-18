#pragma once

#include <vector>
#include <string>
#include <memory>
#include "Clip.h"

namespace mrorchords {
    class TimelineModel {
    public:
        TimelineModel();
        ~TimelineModel();

        // Adds a new clip to the timeline
        // Returns the index of the added clip
        int addClip(const std::shared_ptr<Clip>& clip);

        // Removes a clip from the timeline by index
        // Returns true if removal was successful
        bool removeClip(int index);

        // Moves a clip from one position to another
        // Returns true if the move was successful
        bool moveClip(int fromIndex, int toIndex);

        // Trims the start of a clip
        // Returns true if trimming was successful
        bool trimClipStart(int index, double newStartTime);

        // Trims the end of a clip
        // Returns true if trimming was successful
        bool trimClipEnd(int index, double newEndTime);

        // Splits a clip at the specified time
        // Returns the index of the new clip created after the split
        int splitClip(int index, double splitTime);

        // Deletes a portion of a clip between start and end times
        // Returns true if deletion was successful
        bool deleteClipSection(int index, double startTime, double endTime);

        // Retrieves a clip by index
        std::shared_ptr<Clip> getClip(int index) const;

        // Retrieves the total number of clips in the timeline
        int getClipCount() const;

        // Retrieves the duration of the timeline
        double getDuration() const;

        // Clears all clips from the timeline
        void clear();

        // Undo the last operation
        void undo();

        // Redo the last undone operation
        void redo();

    private:
        std::vector<std::shared_ptr<Clip>> m_clips;
        std::vector<std::pair<std::function<void()>, std::function<void()>>> m_undoStack;
        std::vector<std::pair<std::function<void()>, std::function<void()>>> m_redoStack;

        void pushUndo(std::function<void()> undoFunc, std::function<void()> redoFunc);
        void pushRedo(std::function<void()> undoFunc, std::function<void()> redoFunc);
    };
}
```

```cpp
#include "TimelineModel.h"
#include <algorithm>

namespace mrorchords {

    TimelineModel::TimelineModel() {}

    TimelineModel::~TimelineModel() {}

    int TimelineModel::addClip(const std::shared_ptr<Clip>& clip) {
        m_clips.push_back(clip);
        pushUndo([this, clip]() {
            auto it = std::find(m_clips.begin(), m_clips.end(), clip);
            if (it != m_clips.end()) {
                m_clips.erase(it);
            }
        }, [this, clip]() {
            m_clips.push_back(clip);
        });
        return static_cast<int>(m_clips.size()) - 1;
    }

    bool TimelineModel::removeClip(int index) {
        if (index < 0 || index >= static_cast<int>(m_clips.size())) {
            return false;
        }
        auto clip = m_clips[index];
        m_clips.erase(m_clips.begin() + index);
        pushUndo([this, index, clip]() {
            m_clips.insert(m_clips.begin() + index, clip);
        }, [this, index]() {
            m_clips.erase(m_clips.begin() + index);
        });
        return true;
    }

    bool TimelineModel::moveClip(int fromIndex, int toIndex) {
        if (fromIndex < 0 || fromIndex >= static_cast<int>(m_clips.size()) || toIndex < 0 || toIndex >= static_cast<int>(m_clips.size())) {
            return false;
        }
        auto clip = m_clips[fromIndex];
        m_clips.erase(m_clips.begin() + fromIndex);
        m_clips.insert(m_clips.begin() + toIndex, clip);
        pushUndo([this, fromIndex, toIndex, clip]() {
            m_clips.erase(m_clips.begin() + toIndex);
            m_clips.insert(m_clips.begin() + fromIndex, clip);
        }, [this, fromIndex, toIndex, clip]() {
            m_clips.erase(m_clips.begin() + fromIndex);
            m_clips.insert(m_clips.begin() + toIndex, clip);
        });
        return true;
    }

    bool TimelineModel::trimClipStart(int index, double newStartTime) {
        if (index < 0 || index >= static_cast<int>(m_clips.size())) {
            return false;
        }
        auto clip = m_clips[index];
        double oldStartTime = clip->getStartTime();
        clip->setStartTime(newStartTime);
        pushUndo([this, index, oldStartTime]() {
            m_clips[index]->setStartTime(oldStartTime);
        }, [this, index, newStartTime]() {
            m_clips[index]->setStartTime(newStartTime);
        });
        return true;
    }

    bool TimelineModel::trimClipEnd(int index, double newEndTime) {
        if (index < 0 || index >= static_cast<int>(m_clips.size())) {
            return false;
        }
        auto clip = m_clips[index];
        double oldEndTime = clip->getEndTime();
        clip->setEndTime(newEndTime);
        pushUndo([this, index, oldEndTime]() {
            m_clips[index]->setEndTime(oldEndTime);
        }, [this, index, newEndTime]() {
            m_clips[index]->setEndTime(newEndTime);
        });
        return true;
    }

    int TimelineModel::splitClip(int index, double splitTime) {
        if (index < 0 || index >= static_cast<int>(m_clips.size())) {
            return -1;
        }
        auto clip = m_clips[index];
        if (splitTime <= clip->getStartTime() || splitTime >= clip->getEndTime()) {
            return -1;
        }
        auto newClip = std::make_shared<Clip>(clip->getMediaPath(), splitTime, clip->getEndTime());
        clip->setEndTime(splitTime);
        m_clips.insert(m_clips.begin() + index + 1, newClip);
        pushUndo([this, index, splitTime, newClip]() {
            m_clips.erase(m_clips.begin() + index + 1);
            m_clips[index]->setEndTime(splitTime);
        }, [this, index, splitTime, newClip]() {
            m_clips[index]->setEndTime(splitTime);
            m_clips.insert(m_clips.begin() + index + 1, newClip);
        });
        return index + 1;
    }

    bool TimelineModel::deleteClipSection(int index, double startTime, double endTime) {
        if (index < 0 || index >= static_cast<int>(m_clips[index]->getDuration())) {
            return false;
        }
        auto clip = m_clips[index];
        clip->deleteSection(startTime, endTime);
        pushUndo([this, index, clip]() {
            m_clips[index]->restoreSection(startTime, endTime);
        }, [this, index, clip]() {
            m_clips[index]->deleteSection(startTime, endTime);
        });
        return true;
    }

    std::shared_ptr<Clip> TimelineModel::getClip(int index) const {
        if (index < 0 || index >= static_cast<int>(m_clips.size())) {
            return nullptr;
        }
        return m_clips[index];
    }

    int TimelineModel::getClipCount() const {
        return static_cast<int>(m_clips.size());
    }

    double TimelineModel::getDuration() const {
        double duration = 0.0;
        for (const auto& clip : m_clips) {
            duration = std::max(duration, clip->getEndTime());
        }
        return duration;
    }

    void TimelineModel::clear() {
        m_clips.clear();
        m_undoStack.clear();
        m_redoStack.clear();
    }

    void TimelineModel::undo() {
        if (m_undoStack.empty()) {
            return;
        }
        auto& operation = m_undoStack.back();
        operation.first();
        m_redoStack.push_back(operation);
        m_undoStack.pop_back();
    }

    void TimelineModel::redo() {
        if (m_redoStack.empty()) {
            return;
        }
        auto& operation = m_redoStack.back();
        operation.second();
        m_undoStack.push_back(operation);
        m_redoStack.pop_back();
    }

    void TimelineModel::pushUndo(std::function<void()> undoFunc, std::function<void()> redoFunc) {
        m_undoStack.emplace_back(undoFunc, redoFunc);
        m_redoStack.clear();
    }

    void TimelineModel::pushRedo(std::function<void()> undoFunc, std::function<void()> redoFunc) {
        m_redoStack.emplace_back(undoFunc, redoFunc);
    }
}