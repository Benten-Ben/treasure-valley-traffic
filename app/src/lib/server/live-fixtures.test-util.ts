/**
 * Synthetic test images for the live-image tests. Flat-color JPEGs made with
 * ffmpeg (16×8 and 24×8), and a way to make each one's bytes differ, as a new
 * picture's would. Not camera images.
 */
import { createHash } from 'node:crypto';

export const GRAY_16x8 = Buffer.from(
	'/9j/4AAQSkZJRgABAgAAAQABAAD//gAQTGF2YzYwLjMxLjEwMgD/2wBDAAgoKC8oLzc3Nzc3N0E8QUNDQ0FBQUFDQ0NISEhVVVVISEhDQ0hIUFBVVVxfXFdXVVdfX2RkZHh4c3OMjJGsrM//xABMAAEBAAAAAAAAAAAAAAAAAAAAAwEBAQAAAAAAAAAAAAAAAAAAAgMQAQAAAAAAAAAAAAAAAAAAAAARAQAAAAAAAAAAAAAAAAAAAAD/wAARCAAIABADASIAAhEAAxEA/9oADAMBAAIRAxEAPwCwCJv/2Q==',
	'base64'
);
export const TEAL_24x8 = Buffer.from(
	'/9j/4AAQSkZJRgABAgAAAQABAAD//gAQTGF2YzYwLjMxLjEwMgD/2wBDAAgoKC8oLzc3Nzc3N0E8QUNDQ0FBQUFDQ0NISEhVVVVISEhDQ0hIUFBVVVxfXFdXVVdfX2RkZHh4c3OMjJGsrM//xABNAAEBAAAAAAAAAAAAAAAAAAAABAEBAQEAAAAAAAAAAAAAAAAAAAUGEAEAAAAAAAAAAAAAAAAAAAAAEQEAAAAAAAAAAAAAAAAAAAAA/8AAEQgACAAYAwEiAAIRAAMRAP/aAAwDAQACEQMRAD8AgAV2OAAf/9k=',
	'base64'
);

export const sha = (b: Uint8Array) => createHash('sha256').update(b).digest('hex');

/** The same picture with a JPEG comment: different bytes, as a new 511 picture would have. */
export function variant(jpeg: Buffer, n: number): Buffer {
	const body = Buffer.from(`synthetic ${n}`);
	const seg = Buffer.alloc(4 + body.length);
	seg[0] = 0xff;
	seg[1] = 0xfe;
	seg.writeUInt16BE(body.length + 2, 2);
	body.copy(seg, 4);
	return Buffer.concat([jpeg.subarray(0, 2), seg, jpeg.subarray(2)]);
}
