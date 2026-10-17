import {describe,expect,it} from 'vitest';
import {broadcastValue,parseBroadcast} from './vk';

describe('one VK broadcast field',()=>{
 it('takes the player and the plain link from the embed code',()=>{
  const code='<iframe src="https://vk.com/video_ext.php?oid=-123&amp;id=456&amp;hash=ab" width="853" allow="autoplay" frameborder="0"></iframe>';
  expect(parseBroadcast(code)).toEqual({broadcast_url:'https://vk.com/video-123_456',broadcast_embed_url:'https://vk.com/video_ext.php?oid=-123&id=456&hash=ab'});
  expect(parseBroadcast('https://vk.com/video_ext.php?oid=-123&id=456')).toMatchObject({broadcast_url:'https://vk.com/video-123_456'});
 });
 it('keeps a plain link as a link to watch in VK',()=>{
  expect(parseBroadcast(' https://vkvideo.ru/video-123_456 ')).toEqual({broadcast_url:'https://vkvideo.ru/video-123_456',broadcast_embed_url:null});
  expect(parseBroadcast('')).toEqual({broadcast_url:null,broadcast_embed_url:null});
 });
 it('rejects other sites and broken player addresses',()=>{
  expect(parseBroadcast('https://youtube.com/watch?v=1')).toHaveProperty('error');
  expect(parseBroadcast('http://vk.com/video-1_2')).toHaveProperty('error');
  expect(parseBroadcast('https://vk.com/video_ext.php?oid=x&id=2')).toHaveProperty('error');
  expect(parseBroadcast('просто текст')).toHaveProperty('error');
 });
 it('shows the player in the field when there is one',()=>{
  expect(broadcastValue('https://vk.com/video-1_2','https://vk.com/video_ext.php?oid=-1&id=2')).toBe('https://vk.com/video_ext.php?oid=-1&id=2');
  expect(broadcastValue('https://vk.com/video-1_2',null)).toBe('https://vk.com/video-1_2');
 });
});
