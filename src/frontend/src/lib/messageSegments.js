/** @param {Array<Record<string, any>> | undefined} segments */
export function normalizedSegments(segments) {
  return segments && segments.length ? segments : [];
}

/**
 * @param {{ role: string, content: string, segments?: Array<Record<string, any>>, streaming?: boolean }} message
 * @param {Array<Record<string, any>>} characters
 */
export function displayMessageSegments(message, characters) {
  if (message.role !== "assistant") {
    return [{ type: "text", content: message.content || "" }];
  }
  const baseSegments = normalizedSegments(message.segments).length
    ? normalizedSegments(message.segments)
    : [{ type: "text", content: message.content || "" }];
  const result = baseSegments.flatMap((segment) => {
    if (segment.type !== "text" || typeof segment.content !== "string") {
      return [segment];
    }
    return visibleTextSegments(segment.content, characters);
  });
  if (message.streaming && result.length > 0) {
    const last = result[result.length - 1];
    if (last.type === "text") {
      const match = last.content.match(/<(think|thinking|reasoning)\b[^>]*>([\s\S]*)$/i);
      if (match) {
        result.pop();
        const before = last.content.slice(0, match.index);
        if (before.trim()) {
          result.push(...dialogueSegments(before, characters));
        }
        result.push({ type: "meta", tag: match[1].toLowerCase(), content: match[2], live: true });
      }
    }
  }
  return result;
}

/**
 * @param {string} content
 * @param {Array<Record<string, any>>} characters
 */
export function visibleTextSegments(content, characters) {
  /** @type {Array<Record<string, any>>} */
  const result = [];
  for (const segment of metaTagSegments(content)) {
    if (segment.type === "meta") {
      result.push(segment);
    } else {
      result.push(...dialogueSegments(segment.content, characters));
    }
  }
  return result;
}

/** @param {string} content */
export function metaTagSegments(content) {
  const result = [];
  const pattern = /<(think|thinking|reasoning)\b[^>]*>([\s\S]*?)<\/\1>/gi;
  let cursor = 0;
  let match;
  while ((match = pattern.exec(content)) !== null) {
    if (match.index > cursor) {
      result.push({ type: "text", content: content.slice(cursor, match.index) });
    }
    result.push({
      type: "meta",
      tag: match[1].toLowerCase(),
      content: match[2].trim(),
    });
    cursor = pattern.lastIndex;
  }
  if (cursor < content.length) {
    result.push({ type: "text", content: content.slice(cursor) });
  }
  return result.length ? result : [{ type: "text", content }];
}

/**
 * @param {string} content
 * @param {Array<Record<string, any>>} characters
 */
export function dialogueSegments(content, characters) {
  const result = [];
  let textBuffer = "";
  for (const rawLine of content.split(/(?<=\n)/)) {
    const line = rawLine.endsWith("\n") ? rawLine.slice(0, -1) : rawLine;
    const newline = rawLine.endsWith("\n") ? "\n" : "";
    const match = line.match(/^\s*\[([^\]]+)\]\s*[:：]\s*「([^」]*)」\s*$/);
    const character = match ? characterByAlias(characters, match[1].trim()) : null;
    if (match && character?.bustup_exists) {
      if (textBuffer) {
        result.push({ type: "text", content: textBuffer });
        textBuffer = "";
      }
      result.push({
        type: "character_dialogue",
        character,
        speaker: character.short_name || character.name || match[1].trim(),
        dialogue: match[2],
      });
      if (newline) {
        textBuffer += newline;
      }
    } else {
      textBuffer += rawLine;
    }
  }
  if (textBuffer) {
    result.push({ type: "text", content: textBuffer });
  }
  return result;
}

/**
 * @param {Array<Record<string, any>>} characters
 * @param {string} alias
 */
export function characterByAlias(characters, alias) {
  return characters.find((character) => {
    const aliases = Array.isArray(character.aliases) ? character.aliases : [];
    return [character.id, character.name, character.short_name, ...aliases]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase() === alias.toLowerCase());
  });
}
