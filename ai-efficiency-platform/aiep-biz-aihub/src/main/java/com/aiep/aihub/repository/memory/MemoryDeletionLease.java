package com.aiep.aihub.repository.memory;

import java.security.MessageDigest;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.HexFormat;
import javax.sql.DataSource;
import org.springframework.stereotype.Repository;

/** 会话锁跨越外部调用但不打开业务事务；租约过期仍不能并行外发同一事件。 */
@Repository
public class MemoryDeletionLease {
 private final DataSource source;
 public MemoryDeletionLease(DataSource source){this.source=source;}
 public boolean run(MemoryLifecycleMapper.Delivery delivery,Runnable action){
  String key;
  try{var hash=MessageDigest.getInstance("SHA-256");hash.update(delivery.tenantId());hash.update((byte)0);hash.update(delivery.eventId());key=HexFormat.of().formatHex(hash.digest());}
  catch(java.security.NoSuchAlgorithmException error){throw new IllegalStateException("MEMORY_LEASE_UNAVAILABLE");}
  try(Connection connection=source.getConnection()){
   if(!connection.getAutoCommit())throw new SQLException("MEMORY_LEASE_AUTOCOMMIT_REQUIRED");
   boolean locked;
   try(var statement=connection.prepareStatement("SELECT GET_LOCK(?,0)")){statement.setString(1,key);try(var rows=statement.executeQuery()){locked=rows.next()&&rows.getInt(1)==1;}}
   if(!locked)return false;
   try{action.run();return true;}
   finally{try(var statement=connection.prepareStatement("SELECT RELEASE_LOCK(?)")){statement.setString(1,key);try(var rows=statement.executeQuery()){if(!rows.next()||rows.getInt(1)!=1)connection.abort(Runnable::run);}}
    catch(SQLException error){connection.abort(Runnable::run);throw error;}}
  }catch(SQLException error){throw new IllegalStateException("MEMORY_LEASE_UNAVAILABLE");}
 }
}
