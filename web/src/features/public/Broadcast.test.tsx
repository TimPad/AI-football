import {describe,expect,it} from 'vitest';
import {render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Broadcast} from './Broadcast';
import type {PublicMatch} from '../../api/domain';

describe('broadcast',()=>{
 it('creates the iframe only after the viewer asks and keeps the VK fallback',async()=>{
  const match={home_name:'Север',away_name:'Юг',broadcast_url:'https://vk.com/video-1_2',broadcast_embed_url:'https://vk.com/video_ext.php?oid=-1&id=2'} as PublicMatch;
  const {container}=render(<Broadcast match={match}/>);
  expect(container.querySelector('iframe')).toBeNull();
  expect(screen.getByRole('link',{name:/Смотреть в ВК/})).toHaveAttribute('href',match.broadcast_url);
  await userEvent.setup().click(screen.getByRole('button',{name:'Смотреть на сайте'}));
  expect(container.querySelector('iframe')).toHaveAttribute('src',match.broadcast_embed_url);
 });
});
