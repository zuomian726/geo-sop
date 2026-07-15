<?php
declare(strict_types=1);

function geo_remote_status_transition_allowed(string $current, string $next): bool {
    if ($current === $next) return true;

    $transitions = [
        'claimed' => ['imported', 'queued', 'running', 'completed', 'failed', 'stopped', 'skipped'],
        'imported' => ['queued', 'running', 'completed', 'failed', 'stopped', 'skipped'],
        'queued' => ['running', 'completed', 'failed', 'stopped', 'skipped'],
        'running' => ['completed', 'failed', 'stopped', 'skipped'],
    ];
    return in_array($next, $transitions[$current] ?? [], true);
}
